import hashlib, os
path = os.path.join(os.path.dirname(__file__), '..', 'Nuevo', 'ENERO 2026 - Con Axarquia.xlsx')
with open(path, 'rb') as f:
    h = hashlib.sha256(f.read()).hexdigest()
print('SHA256:', h)
print('Size:', os.path.getsize(path), 'bytes')
