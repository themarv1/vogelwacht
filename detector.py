"""Vogelerkennung auf der Torq-NPU.

Nutzt das YOLOv8n-Modell (COCO, Klasse "bird") und die Hilfsfunktionen aus
dem Beispiel `object_detection` von Synaptics (sl2610-examples). Dadurch
sind Vor- und Nachbearbeitung genau die, mit denen Synaptics das Modell
getestet hat.
"""

import os
import sys


class BirdDetector:
    def __init__(self, examples_dir, model_path, labels_path, conf=0.35, device='torq'):
        od_dir = os.path.join(examples_dir, 'object_detection')
        for p in (examples_dir, od_dir):
            if p not in sys.path:
                sys.path.insert(0, p)
        import results  # noqa: E402  (aus sl2610-examples/object_detection)
        import vision  # noqa: E402
        from app_utils.npu import cleanup_npu_after_inference, setup_npu_for_inference
        from app_utils.torq_examples.utils.inference import SimpleVMFBInferenceRunner

        self._vision = vision
        self._cleanup = cleanup_npu_after_inference
        self.conf = conf
        self.labels = results.load_labels(labels_path)
        setup_npu_for_inference()
        self.runner = SimpleVMFBInferenceRunner(
            model_path, device_uri=device, function='main', load_model_to_mem=True,
            device_io=True,  # wie im Synaptics-Beispiel: dmabuf braucht Geraete-I/O
        )

    def detect(self, bgr):
        """Liefert [(score, (x, y, w, h)), ...] fuer alle Voegel im Bild."""
        v = self._vision
        inp, pad_info, orig_shape = v.preprocess_frame(bgr)
        raw = self.runner.infer(inp)
        out = v.dequantize_out(raw)
        dets = v.postprocess(out, orig_shape, pad_info, self.labels, conf_thresh=self.conf)
        return [(float(score), tuple(int(c) for c in box)) for label, score, box in dets if label == 'bird']

    @property
    def infer_ms(self):
        return getattr(self.runner, 'infer_time_ms', None)

    def close(self):
        self._cleanup()
