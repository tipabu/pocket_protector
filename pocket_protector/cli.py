# -*- coding: utf-8 -*-

import os
import sys
import json
import getpass
import difflib
import argparse

from _version import __version__
from file_keys import KeyFile, Creds

_ANSI_FORE_RED = '\x1b[31m'
_ANSI_FORE_GREEN = '\x1b[32m'
_ANSI_RESET_ALL = '\x1b[0m'

# TODO: custodian-signed values. allow custodians to sign values
# added/set by others, then produced reports on which keys have been
# updated/changed but not signed yet. enables a review/audit mechanism.

def get_argparser():
    """
    args:

    path to file
    confirm-diff

    actions:

    init - done
    add key custodian - done
    add domain - done
    grant access - done
    set secret - done (TODO: split into add/update)
    set key custodian passphrase - done
    remove key custodian - needs backend
    remove domain - needs backend
    remove owner - needs backend
    remove secret - needs backend
    truncate audit log - needs backend
    rotate key domain keypair - done
    rotate key custodian keypair - done
    # both rotations require creds but externally-used creds (passphrases) stay the same

    read-only:

    list domains
    list all keys (with list of domains with the key)
    list keys accessible by X

    # TODO: flag for username on the commandline (-u)
    # TODO: allow passphrase as envvar
    # TODO: catch KeyboardInterrupt
    """
    prs = argparse.ArgumentParser()
    prs.add_argument('--file',
                     help='the file to pocket protect, defaults to protected.yaml in the working directory')
    prs.add_argument('--confirm-diff', action='store_true',
                     help='show diff before modifying the file')
    subprs = prs.add_subparsers(dest='action')

    subprs.add_parser('init')
    subprs.add_parser('version')
    subprs.add_parser('add-key-custodian')
    subprs.add_parser('add-domain')
    subprs.add_parser('add-owner')
    subprs.add_parser('set-secret')
    subprs.add_parser('set-key-custodian-passphrase')
    subprs.add_parser('decrypt-domain')

    return prs


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    prs = get_argparser()

    kwargs = dict(prs.parse_args()._get_kwargs())
    action = kwargs['action']
    file_path = kwargs.get('file') or 'protected.yaml'
    file_abs_path = os.path.abspath(file_path)

    if action == 'version':
        print('pocket_protector version %s' % __version__)
        sys.exit(0)

    if action == 'init':
        if os.path.exists(file_abs_path):
            print('File already exists: %s' % file_abs_path)
            sys.exit(2)
        with open(file_abs_path, 'wb') as f:
            f.write('')  # TODO
            # TODO: automatically remove file if init fails
        kf = KeyFile(path=file_abs_path)
        # TODO: add audit log entry for creation date
        # TODO: add audit log dates in general
    else:
        if not os.path.exists(file_abs_path):
            print('File not found: %s' % file_path)
            sys.exit(2)
        kf = KeyFile.from_file(file_abs_path)
    modified_kf = None

    if action == 'init' or action == 'add-key-custodian':
        print 'Adding new key custodian.'
        creds = get_creds(confirm_pass=True)
        modified_kf = kf.add_key_custodian(creds)
    elif action == 'add-domain':
        print 'Adding new domain.'
        creds = check_creds(kf, get_creds())
        domain_name = raw_input('Domain name: ')
        modified_kf = kf.add_domain(domain_name, creds.name)
    elif action == 'set-secret':
        print 'Setting secret value.'
        domain_name = raw_input('Domain name: ')
        secret_name = raw_input('Secret name: ')
        secret_value = raw_input('Secret value: ')  # TODO: getpass?
        modified_kf = kf.set_secret(domain_name, secret_name, secret_value)
    elif action == 'add-owner':
        print 'Adding domain owner.'
        creds = check_creds(kf, get_creds())
        domain_name = raw_input('Domain name: ')
        new_owner_name = raw_input('New owner email: ')
        modified_kf = kf.add_owner(domain_name, new_owner_name, creds)
    elif action == 'set-key-custodian-passphrase':
        user_id = raw_input('User email: ')
        passphrase = get_pass(confirm_pass=False, label='Current passphrase')
        creds = Creds(user_id, passphrase)
        check_creds(kf, creds)
        new_passphrase = get_pass(confirm_pass=True,
                                  label='New passphrase',
                                  label2='Retype new passphrase')
        modified_kf = kf.set_key_custodian_passphrase(creds, new_passphrase)
    elif action == 'decrypt-domain':
        creds = check_creds(kf, get_creds())
        domain_name = raw_input('Domain name: ')
        decrypted_dict = kf.decrypt_domain(domain_name, creds)
        print json.dumps(decrypted_dict, indent=2, sort_keys=True)
    elif action == 'rotate-domain-key':
        creds = check_creds(kf, get_creds())
        domain_name = raw_input('Domain name: ')
        modified_kf = kf.rotate_domain_key(domain_name, creds)
    elif action == 'rotate-key-custodian-key':
        creds = check_creds(kf, get_creds())
        modified_kf = kf.rotate_key_custodian_key(creds)
    else:
        raise NotImplementedError('Unrecognized subcommand: %s' % action)

    if kwargs['confirm_diff']:
        diff_lines = list(difflib.unified_diff(kf.get_contents().splitlines(),
                                               modified_kf.get_contents().splitlines(),
                                               file_path + '.old', file_path + '.new'))
        diff_lines = _get_colorized_lines(diff_lines)
        print 'Changes to be written:\n'
        print '\n'.join(diff_lines)
        print
        do_write = raw_input('Write changes? [y/N] ')
        if not do_write.lower().startswith('y'):
            print 'Aborting...'
            sys.exit(0)

    if modified_kf:
        modified_kf.write()

    return


def _get_colorized_lines(lines):
    ret = []
    colors = {'-': _ANSI_FORE_RED, '+': _ANSI_FORE_GREEN}
    for line in lines:
        if line[0] in colors:
            line = colors[line[0]] + line + _ANSI_RESET_ALL
        ret.append(line)
    return ret


def check_creds(kf, creds):
    if not kf.check_creds(creds):
        print 'Invalid user credentials. Check email and passphrase and try again.'
        sys.exit(1)
    return creds


def get_creds(confirm_pass=False):
    user_id = raw_input('User email: ')
    passphrase = get_pass(confirm_pass=confirm_pass)
    ret = Creds(user_id, passphrase)
    return ret


def get_pass(confirm_pass=False, label='Passphrase', label2='Retype passphrase'):
    passphrase = getpass.getpass('%s: ' % label)
    if confirm_pass:
        passphrase2 = getpass.getpass('%s: ' % label2)
        if passphrase != passphrase2:
            print 'Sorry, passphrases did not match.'
            sys.exit(1)
    return passphrase


# TODO: allow separate env vars
def full_get_creds(args=None, env_var_prefix='PPROTECT_'):
    # prefer command line
    # TODO: pick up quiet flag
    user = None
    if args:
        user = getattr(args, 'user')

    # then check environment variables

    user_env_var_name = env_var_prefix + 'USER'
    passphrase_env_var_name = env_var_prefix + 'PASSPHRASE'
    # try and fail with clean error if incorrect (with a warning if it's empty)

    # finally ask on stdin (but only if not quiet)

    # Failed to read valid PocketProtector passphrase (for user XXX)
    # from stdin and <passphrase_env_var_name> was not set. (XYZError:
    # was not set)

if __name__ == '__main__':
    sys.exit(main(sys.argv) or 0)
