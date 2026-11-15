"""Artbestimmung auf der CPU mit dem iNaturalist-Vogelmodell von Google Coral.

MobileNetV2, 224 x 224, quantisiert (uint8), 964 Vogelarten. Laeuft mit
LiteRT (ai-edge-litert) bzw. tflite-runtime auf der CPU, weil es noch nicht
fuer die Torq-NPU uebersetzt ist. Pro Besuch werden nur wenige Ausschnitte
klassifiziert, dafuer reicht die CPU.
"""

import cv2
import numpy as np

try:
    from ai_edge_litert.interpreter import Interpreter
except ImportError:  # aelterer Paketname
    from tflite_runtime.interpreter import Interpreter


def latin_name(label):
    """'Parus major (Great Tit)' -> 'Parus major'"""
    return label.split(' (')[0].strip()


def english_name(label):
    """'Parus major (Great Tit)' -> 'Great Tit'"""
    if '(' in label:
        return label[label.index('(') + 1:].rstrip(')').strip()
    return label


def load_labels(path):
    labels = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Format "Name" oder "<index> Name"
            head, _, rest = line.partition(' ')
            labels.append(rest.strip() if head.isdigit() and rest else line)
    return labels


class SpeciesClassifier:
    def __init__(self, model_path, labels_path, allowed=None, threads=2):
        self.interp = Interpreter(model_path=model_path, num_threads=threads)
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.out = self.interp.get_output_details()[0]
        self.size = (int(self.inp['shape'][2]), int(self.inp['shape'][1]))  # (w, h)
        self.labels = load_labels(labels_path)
        n_out = int(np.prod(self.out['shape']))
        # Manche Modelle haben eine zusaetzliche Klasse "background"
        while len(self.labels) < n_out:
            self.labels.append('background')
        self.full = {latin_name(l): l for l in self.labels}
        if allowed:
            wanted = set(allowed)
            self.idx = np.array([i for i, l in enumerate(self.labels) if latin_name(l) in wanted])
            missing = wanted - {latin_name(self.labels[i]) for i in self.idx}
            if missing:
                print('Hinweis: nicht im Artmodell enthalten:', ', '.join(sorted(missing)))
        else:
            self.idx = np.array([i for i, l in enumerate(self.labels) if l != 'background'])

    def _prepare(self, bgr):
        rgb = cv2.cvtColor(cv2.resize(bgr, self.size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        dtype = self.inp['dtype']
        if dtype == np.uint8:
            data = rgb
        elif dtype == np.int8:
            data = (rgb.astype(np.int16) - 128).astype(np.int8)
        else:
            data = rgb.astype(np.float32) / 127.5 - 1.0
        return np.expand_dims(data, 0)

    def classify(self, bgr, top_k=5):
        """Liefert [(lateinischer Name, Wahrscheinlichkeit), ...] absteigend."""
        self.interp.set_tensor(self.inp['index'], self._prepare(bgr))
        self.interp.invoke()
        raw = self.interp.get_tensor(self.out['index']).reshape(-1)
        scale, zp = self.out.get('quantization', (0.0, 0))
        if scale:
            probs = (raw.astype(np.float32) - zp) * scale
        else:
            probs = raw.astype(np.float32)
            if probs.min() < 0 or probs.sum() > 1.5:  # Logits -> Softmax
                e = np.exp(probs - probs.max())
                probs = e / e.sum()
        probs = np.clip(probs[self.idx], 0, None)
        total = probs.sum()
        if total <= 0:
            return []
        probs = probs / total  # auf die erlaubten Arten normieren
        order = np.argsort(probs)[::-1][:top_k]
        return [(latin_name(self.labels[self.idx[i]]), float(probs[i])) for i in order]

    def display_name(self, latin, german):
        """Deutscher Name, sonst englischer Name aus der Labeldatei."""
        if latin in german:
            return german[latin]
        return english_name(self.full.get(latin, latin))
