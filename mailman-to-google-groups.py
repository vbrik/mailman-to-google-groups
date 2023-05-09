#!/usr/bin/env python
import argparse
import subprocess
import sys
import logging
from pprint import pprint
from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError

def get_mailman_list_config(hostname, list_email, bin_dir):
    list_name = list_email.split("@")[0]

    cfg = {"email": list_email}

    out = subprocess.check_output(
        ["ssh", hostname, bin_dir + "/config_list", "-o", "-", list_name]
    )
    exec(out, None, cfg)

    out = subprocess.check_output(
        ["ssh", hostname, bin_dir + "/list_members", "--digest", list_name]
    )
    cfg["digest_members"] = [
        line.strip().decode("ascii") for line in out.split(b"\n") if line.strip()
    ]

    out = subprocess.check_output(
        ["ssh", hostname, bin_dir + "/list_members", "--regular", list_name]
    )
    cfg["regular_members"] = [
        line.strip().decode("ascii") for line in out.split(b"\n") if line.strip()
    ]

    return cfg


def mailman_to_google_group_config(mmcfg):
    # https://developers.google.com/admin-sdk/groups-settings/v1/reference/groups#json
    if mmcfg["advertised"] and mmcfg["archive"]:
        if mmcfg["archive_private"]:
            who_can_view_group = "ALL_MEMBERS_CAN_VIEW"
        else:
            who_can_view_group = "ALL_IN_DOMAIN_CAN_VIEW"
    else:  # not advertised or not archived
        who_can_view_group = "ALL_MANAGERS_CAN_VIEW"

    if mmcfg["generic_nonmember_action"] in (0, 1):  # accept, hold
        who_can_post_message = "ANYONE_CAN_POST"
    else:  # reject, discard
        who_can_post_message = "ALL_MEMBERS_CAN_POST"
    if (
        mmcfg["default_member_moderation"] and mmcfg["member_moderation_action"] != 0
    ):  # hold
        who_can_post_message = "NONE_CAN_POST"

    if mmcfg["generic_nonmember_action"] == 0:  # accept
        message_moderation_level = "MODERATE_NONE"
    else:  # hold, reject, discard
        message_moderation_level = "MODERATE_NON_MEMBERS"
    if mmcfg["default_member_moderation"]:
        message_moderation_level = "MODERATE_ALL_MESSAGES"

    ggcfg = {
        "email": mmcfg["email"],
        "name": mmcfg["real_name"],
        "description": (
            mmcfg["description"] + b"\n" + mmcfg["info"]
            if mmcfg["info"]
            else mmcfg["description"]
        ),
        "whoCanJoin": "CAN_REQUEST_TO_JOIN",
        "whoCanViewMembership": "ALL_IN_DOMAIN_CAN_VIEW",
        "whoCanViewGroup": who_can_view_group,
        "allowExternalMembers": "true",  # tighten later
        "whoCanPostMessage": who_can_post_message,
        "allowWebPosting": "true",
        "primaryLanguage": "en",
        "isArchived": ("true" if mmcfg["archive"] else "false"),
        "archiveOnly": "false",
        "messageModerationLevel": message_moderation_level,
        "spamModerationLevel": "MODERATE",  # this is the default
        "replyTo": "REPLY_TO_IGNORE",  # users individually decide where the message reply is sent.
        # "customReplyTo": "",  # only if replyTo is REPLY_TO_CUSTOM
        "includeCustomFooter": "false",
        # "customFooterText": ""  # only if includeCustomFooter,
        "sendMessageDenyNotification": "false",  # to not have to set defaultMessageDenyNotificationText
        # "defaultMessageDenyNotificationText": "",
        "membersCanPostAsTheGroup": "false",
        "includeInGlobalAddressList": "false",  # has to do with Outlook integration
        "whoCanLeaveGroup": (
            "ALL_MEMBERS_CAN_LEAVE" if mmcfg["unsubscribe_policy"] else "NONE_CAN_LEAVE"
        ),
        "whoCanContactOwner": "ALL_IN_DOMAIN_CAN_CONTACT",
        "favoriteRepliesOnTop": "false",
        "whoCanApproveMembers": "ALL_OWNERS_CAN_APPROVE",  # XXX we want custom role to do this
        "whoCanBanUsers": "OWNERS_AND_MANAGERS",
        "whoCanModerateMembers": "OWNERS_AND_MANAGERS",  # XXX we want custom role to do this
        "whoCanModerateContent": "OWNERS_AND_MANAGERS",  # XXX we want custom role to do this
        "whoCanAssistContent": "NONE",  # has something to do with collaborative inbox
        "enableCollaborativeInbox": "false",
        "whoCanDiscoverGroup": (
            "ALL_IN_DOMAIN_CAN_DISCOVER"
            if mmcfg["advertised"]
            else "ALL_MEMBERS_CAN_DISCOVER"
        ),
        # "defaultSender": "DEFAULT_SELF",  # only matters if posting as group is enabled
    }
    return ggcfg


def main():
    parser = argparse.ArgumentParser(
        description="",
        epilog="Notes:\n"
        "[1] The service account needs to be set up for domain-wide delegation.\n"
        "[2] The delegate account needs to have a Google Workspace admin role.\n"
        "XXX which APIs to enable",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--list", metavar="EMAIL", required=True, help="list email")
    parser.add_argument(
        "--host", metavar="NAME", required=True, help="mailman host to ssh to"
    )
    parser.add_argument(
        "--mailman-bin-dir",
        metavar="PATH",
        default="/usr/lib/mailman/bin/",
        help="mailman bin directory (default: /usr/lib/mailman/bin/)",
    )
    parser.add_argument(
        "--sa-creds",
        metavar="PATH",
        required=True,
        help="service account credentials JSON¹",
    )
    parser.add_argument(
        "--sa-delegate",
        metavar="EMAIL",
        required=True,
        help="the principal whom the service account will impersonate²",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error"),
        help="logging level (default: info)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)-23s %(levelname)s %(message)s",
    )

    logging.info(f"Retrieving mailman list configuration of {args.list}")
    mmcfg = get_mailman_list_config(args.host, args.list, args.mailman_bin_dir)
    logging.info("Converting mailman list settings to google group settings")
    ggcfg = mailman_to_google_group_config(mmcfg)

    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.group",
        "https://www.googleapis.com/auth/admin.directory.group.member",
        "https://www.googleapis.com/auth/apps.groups.settings",
    ]

    creds = service_account.Credentials.from_service_account_file(
        args.sa_creds, scopes=SCOPES, subject=args.sa_delegate
    )

    with discovery.build("admin", "directory_v1", credentials=creds) as svc:
        try:
            logging.info(f"Creating group {ggcfg['email']}")
            svc.groups().insert(body={
                "description": ggcfg['description'],
                "email": ggcfg["email"],
                "name": ggcfg["name"],
            }).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                pass
            else:
                raise




    return
    service = discovery.build("groupssettings", "v1", credentials=creds)
    groups = service.groups()
    req = groups.get(groupUniqueId="vbrik-test-group-1@icecube.wisc.edu")
    res = req.execute()
    pprint(res)

    req = groups.patch(
        groupUniqueId="vbrik-test-group-1@icecube.wisc.edu",
        body={"description": "test testt test"},
    )
    res = req.execute()
    pprint(res)
    service.close()


#    with open(listname + '.pkl', 'wb') as f:
#        pickle.dump(cfg, f)


if __name__ == "__main__":
    sys.exit(main())
