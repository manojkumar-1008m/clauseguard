import csv, pathlib
from clauseguard.backend import model_loader, preprocessing
ROOT = pathlib.Path('clauseguard/tests/hard_negative_regression.csv')
correct = 0
total = 0
with open(ROOT, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        cleaned = preprocessing.preprocess(row['text'])
        pred, _ = model_loader.predict(cleaned)
        if pred == 0:
            correct += 1
print('Accuracy:', correct / total)
