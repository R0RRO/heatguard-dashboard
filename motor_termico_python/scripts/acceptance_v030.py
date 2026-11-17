import argparse
import json

from heatguard.release_acceptance import run_release_acceptance


def main():
    parser=argparse.ArgumentParser(description='Aceptación integral simulada HeatGuard v0.30')
    parser.add_argument('--out',default='results/release_v030')
    parser.add_argument('--db',default='results/release_v030/acceptance.sqlite')
    args=parser.parse_args()
    print(json.dumps(run_release_acceptance(args.out,args.db),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
