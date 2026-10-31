"""Import UTF-8 .txt/.md files through the API. Worker and publish stay explicit."""
import argparse
import os
from pathlib import Path
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    parser.add_argument('--source-id',required=True)
    parser.add_argument('--revision',type=int,default=1)
    parser.add_argument('--kind',choices=['standard','case'],default='standard')
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    args = parser.parse_args()
    if args.file.suffix.lower() not in {'.md','.txt'}:
        parser.error('Local baseline supports UTF-8 .md and .txt only; PDF/OCR/DOCX adapters are not implemented')
    if args.file.stat().st_size > 3_000_000:
        parser.error('File too large for local text ingestion')
    token=os.environ.get('TOWER_DEV_TOKEN')
    if not token: parser.error('Export TOWER_DEV_TOKEN first')
    # Localhost does not need the external credential-injecting proxy.
    with httpx.Client(trust_env=False,timeout=30) as client:
        response=client.post(args.url.rstrip('/')+'/api/v1/documents',
            headers={'Authorization':'Bearer '+token},
            json={'title':args.file.name,'source_id':args.source_id,'source_revision':args.revision,
                  'source_kind':args.kind,'content':args.file.read_text(encoding='utf-8')})
        response.raise_for_status()
        print(response.text)

if __name__=='__main__': main()
