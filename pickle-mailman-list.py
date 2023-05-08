#!/usr/bin/env python
import argparse
import pickle
import subprocess
import sys
from pprint import pprint


def main():
    parser = argparse.ArgumentParser(
            description="Save in LIST.pkl the settings and members of a mailman "
                        "mailing list.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('list', metavar='LIST', help='list name')
    parser.add_argument('--bin-dir', metavar='PATH', default='/usr/lib/mailman/bin/',
                        help='mailman bin directory')
    args = parser.parse_args()

    p = subprocess.Popen([args.bin_dir + '/config_list', '-o', '-', args.list],
                         stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    cfg = {}
    exec(stdout, None, cfg)

    p = subprocess.Popen([args.bin_dir + '/list_members', '--digest', args.list],
                         stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    cfg['digest_members'] = [l.strip() for l in stdout.split('\n')]

    p = subprocess.Popen([args.bin_dir + '/list_members', '--regular', args.list],
                         stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    cfg['regular_members'] = [l.strip() for l in stdout.split('\n')]

    pickle.dump(cfg, open(args.list + '.pkl', 'w'))


if __name__ == '__main__':
    sys.exit(main())

