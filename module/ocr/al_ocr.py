import os

import cv2
import numpy as np
from PIL import Image
from cnocr import CnOcr
from cnocr.cn_ocr import data_dir, read_charset, check_model_name, load_module, gen_network
from cnocr.hyperparams.cn_hyperparams import CnHyperparams as Hyperparams

from module.logger import logger


class AlOcr(CnOcr):
    def __init__(
        self,
        model_name='densenet-lite-gru',
        model_epoch=None,
        cand_alphabet=None,
        root=data_dir(),
        context='cpu',
        name=None,
    ):

        """

        :param model_name: 模型名称
        :param model_epoch: 模型迭代次数
        :param cand_alphabet: 待识别字符所在的候选集合。默认为 `None`，表示不限定识别字符范围
        :param root: 模型文件所在的根目录。
            Linux/Mac下默认值为 `~/.cnocr`，表示模型文件所处文件夹类似 `~/.cnocr/1.1.0/conv-lite-fc-0027`。
            Windows下默认值为 ``。
        :param context: 'cpu', or 'gpu'。表明预测时是使用CPU还是GPU。默认为CPU。
        :param name: 正在初始化的这个实例名称。如果需要同时初始化多个实例，需要为不同的实例指定不同的名称。
        """
        check_model_name(model_name)
        self._model_name = model_name
        self._model_file_prefix = '{}-{}'.format(self.MODEL_FILE_PREFIX, model_name)
        self._model_epoch = model_epoch

        self._model_dir = root  # Change folder structure.
        self._assert_and_prepare_model_files()
        self._alphabet, self._inv_alph_dict = read_charset(
            os.path.join(self._model_dir, 'label_cn.txt')
        )

        self._cand_alph_idx = None
        self.set_cand_alphabet(cand_alphabet)

        self._hp = Hyperparams()
        self._hp._loss_type = None  # infer mode
        self._hp._num_classes = len(self._alphabet)
        # 传入''的话，也改成传入None
        self._net_prefix = None if name == '' else name

        self._mod = self._get_module(context)

    def _assert_and_prepare_model_files(self):
        model_dir = self._model_dir
        model_files = [
            'label_cn.txt',
            '%s-%04d.params' % (self._model_file_prefix, self._model_epoch),
            '%s-symbol.json' % self._model_file_prefix,
        ]
        file_prepared = True
        for f in model_files:
            f = os.path.join(model_dir, f)
            if not os.path.exists(f):
                file_prepared = False
                logger.warning('can not find file %s', f)
                break

        if file_prepared:
            return

        # Disable auto downloading cnocr models when model not found.
        # get_model_file(model_dir)
        logger.warning(f'Ocr model not prepared: {model_dir}')
        exit(1)

    def _get_module(self, context):
        network, self._hp = gen_network(self._model_name, self._hp, self._net_prefix)
        hp = self._hp
        prefix = os.path.join(self._model_dir, self._model_file_prefix)
        data_names = ['data']
        data_shapes = [(data_names[0], (hp.batch_size, 1, hp.img_height, hp.img_width))]
        logger.info('Loading OCR model: %s' % self._model_dir)  # Change log appearance.
        mod = load_module(
            prefix,
            self._model_epoch,
            data_names,
            data_shapes,
            network=network,
            net_prefix=self._net_prefix,
            context=context,
        )
        return mod

    def _preprocess_img_array(self, img):
        """
        :param img: image array with type mx.nd.NDArray or np.ndarray,
        with shape [height, width] or [height, width, channel].
        channel shoule be 1 (gray image) or 3 (color image).

        :return: np.ndarray, with shape (1, height, width)
        """
        # Resize image using `cv2.resize` instead of `mxnet.image.imresize`
        new_width = int(round(self._hp.img_height / img.shape[0] * img.shape[1]))
        img = cv2.resize(img, (new_width, self._hp.img_height))
        img = np.expand_dims(img, 0).astype('float32') / 255.0
        return img

    def debug(self, img_list):
        """
        Args:
            img_list: List of numpy array, (height, width)
        """
        img_list = [(self._preprocess_img_array(img) * 255.0).astype(np.uint8) for img in img_list]
        img_list, img_widths = self._pad_arrays(img_list)
        image = cv2.hconcat(img_list)[0, :, :]
        Image.fromarray(image).show()
