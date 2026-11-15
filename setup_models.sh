#!/bin/sh
# Laedt das Vogelarten-Modell (iNaturalist, 964 Arten) von Google Coral.
# Das YOLO-Modell fuer die Vogelerkennung kommt aus sl2610-examples
# (dort: object_detection/setup_demo.py).
set -e
cd "$(dirname "$0")"
mkdir -p models
BASE=https://github.com/google-coral/test_data/raw/master
curl -fL -o models/mobilenet_v2_1.0_224_inat_bird_quant.tflite "$BASE/mobilenet_v2_1.0_224_inat_bird_quant.tflite"
curl -fL -o models/inat_bird_labels.txt "$BASE/inat_bird_labels.txt"
ls -l models
