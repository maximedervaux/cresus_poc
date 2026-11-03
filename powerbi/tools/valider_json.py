import json, urllib.request
from pathlib import Path
from jsonschema import Draft7Validator, RefResolver

root=Path(__file__).resolve().parents[1]
cache={}
def get(uri):
    if uri not in cache:
        actual=uri.replace('https://developer.microsoft.com/json-schemas/','https://raw.githubusercontent.com/microsoft/json-schemas/main/')
        actual=actual.replace('schema.embedded.json','schema-embedded.json')
        cache[uri]=json.load(urllib.request.urlopen(actual))
    return cache[uri]
errors=[]; count=0
for file in [*root.rglob('*.json'), *root.glob('*.pbip'), *root.rglob('*.pbism'), *root.rglob('*.pbir')]:
    obj=json.loads(file.read_text(encoding='utf-8-sig'))
    if '$schema' not in obj: continue
    schema=get(obj['$schema'])
    resolver=RefResolver(base_uri=obj['$schema'], referrer=schema, handlers={'https':get})
    for err in Draft7Validator(schema,resolver=resolver).iter_errors(obj):
        errors.append(f'{file.relative_to(root)}: {list(err.path)}: {err.message}')
    count+=1
print('\n'.join(errors) if errors else f'OK : {count} fichiers validés avec les schémas officiels Microsoft')
raise SystemExit(bool(errors))

