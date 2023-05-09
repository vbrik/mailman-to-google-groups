#!/usr/bin/env python
import argparse
import pickle
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(
            description="Save in LIST.pkl the settings and members of a mailman "
                        "mailing list.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('list', metavar='EMAIL', help='list email')
    parser.add_argument('--host', metavar='NAME', required=True,
                        help='mailman host to ssh to')
    parser.add_argument('--bin-dir', metavar='PATH', default='/usr/lib/mailman/bin/',
                        help='mailman bin directory')
    args = parser.parse_args()

    listname = args.list.split('@')[0]

    cfg = {'email': args.list}

    p = subprocess.Popen(['ssh', args.host, args.bin_dir + '/config_list', '-o', '-', listname],
                         stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    exec(stdout, None, cfg)

    p = subprocess.Popen(['ssh', args.host, args.bin_dir + '/list_members', '--digest', listname],
                         stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    cfg['digest_members'] = [l.strip() for l in stdout.split(b'\n')]

    p = subprocess.Popen(['ssh', args.host, args.bin_dir + '/list_members', '--regular', listname],
                         stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    cfg['regular_members'] = [l.strip() for l in stdout.split(b'\n')]

    with open(listname + '.pkl', 'wb') as f:
        pickle.dump(cfg, f)


if __name__ == '__main__':
    sys.exit(main())

