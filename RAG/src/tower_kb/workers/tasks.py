import argparse
import time
from tower_kb.bootstrap import Container
from tower_kb.config import Settings

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true",help="Process at most one durable job")
    args=parser.parse_args()
    c=Container(Settings.from_env())
    while True:
        worked=c.pipeline.run_once()
        if args.once: break
        if not worked: time.sleep(1)

if __name__=="__main__": main()
