#!/usr/bin/env python
import argparse
import sys
import logging
import pickle
import re
from pprint import pformat
from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError


def get_google_group_config_from_mailman_config(mmcfg):
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
    if mmcfg["default_member_moderation"] and mmcfg["member_moderation_action"] in (
        1,
        2,
    ):  # reject or discard
        who_can_post_message = "NONE_CAN_POST"

    if mmcfg["generic_nonmember_action"] == 0:  # accept
        message_moderation_level = "MODERATE_NONE"
    else:  # hold, reject, discard
        message_moderation_level = "MODERATE_NON_MEMBERS"
    if mmcfg["default_member_moderation"]:
        message_moderation_level = "MODERATE_ALL_MESSAGES"

    if mmcfg["private_roster"] == 0:
        who_can_view_membership = "ALL_IN_DOMAIN_CAN_VIEW"
    elif mmcfg["private_roster"] == 1:
        who_can_view_membership = "ALL_MEMBERS_CAN_VIEW"
    else:
        who_can_view_membership = "ALL_MANAGERS_CAN_VIEW"

    ggcfg = {
        "email": mmcfg["email"],
        "name": mmcfg["real_name"],
        "description": (
            mmcfg["description"] + b"\n" + mmcfg["info"]
            if mmcfg["info"]
            else mmcfg["description"]
        ),
        "whoCanJoin": "CAN_REQUEST_TO_JOIN",
        "whoCanViewMembership": who_can_view_membership,
        "whoCanViewGroup": who_can_view_group,
        "allowExternalMembers": "true",  # can't be tighter until we start forcing people to use @iwe addresses
        "whoCanPostMessage": who_can_post_message,
        "allowWebPosting": "true",
        "primaryLanguage": "en",
        "isArchived": ("true" if mmcfg["archive"] else "false"),
        "archiveOnly": "false",
        "messageModerationLevel": message_moderation_level,
        "spamModerationLevel": "MODERATE",  # this is the default
        "replyTo": "REPLY_TO_IGNORE",  # users individually decide where the message reply is sent
        # "customReplyTo": "",  # only if replyTo is REPLY_TO_CUSTOM
        "includeCustomFooter": "false",
        # "customFooterText": ""  # only if includeCustomFooter,
        "sendMessageDenyNotification": "false",
        # "defaultMessageDenyNotificationText": "",  # only matters if sendMessageDenyNotification is true
        "membersCanPostAsTheGroup": "false",
        "includeInGlobalAddressList": "false",  # has to do with Outlook integration
        "whoCanLeaveGroup": (
            "ALL_MEMBERS_CAN_LEAVE" if mmcfg["unsubscribe_policy"] else "NONE_CAN_LEAVE"
        ),
        "whoCanContactOwner": "ALL_IN_DOMAIN_CAN_CONTACT",
        "favoriteRepliesOnTop": "false",
        "whoCanApproveMembers": "ALL_MANAGERS_CAN_APPROVE",
        "whoCanBanUsers": "OWNERS_AND_MANAGERS",
        "whoCanModerateMembers": "OWNERS_AND_MANAGERS",
        "whoCanModerateContent": "OWNERS_AND_MANAGERS",
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
        description="Import mailman list configuration (settings and members) created\n"
        "by `pickle-mailman-list.py` into Google Groups using Google API¹.",
        epilog="Notes:\n"
        "[1] The following APIs must be enabled: Admin SDK, Group Settings.\n"
        "[2] The service account needs to be set up for domain-wide delegation.\n"
        "[3] The delegate account needs to have a Google Workspace admin role.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--list-pkl",
        metavar="PATH",
        required=True,
        help="mailman list configuration pickle created by pickle-mailman-list.py",
    )
    parser.add_argument(
        "--ignore",
        metavar="EMAIL",
        default=[],
        nargs="*",
        help="don't add EMAIL to group members",
    )
    parser.add_argument(
        "--sa-creds",
        metavar="PATH",
        required=True,
        help="service account credentials JSON²",
    )
    parser.add_argument(
        "--sa-delegate",
        metavar="EMAIL",
        required=True,
        help="the principal whom the service account will impersonate³",
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
        format="%(levelname)s %(message)s",
    )

    logging.info(f"Retrieving mailman list configuration from {args.list_pkl}")
    with open(args.list_pkl, "rb") as f:
        mmcfg = pickle.load(f)
    logging.debug(pformat(mmcfg))
    logging.info("Converting mailman list settings to google group settings")
    ggcfg = get_google_group_config_from_mailman_config(mmcfg)
    logging.debug(pformat(ggcfg))

    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.group",
        "https://www.googleapis.com/auth/admin.directory.group.member",
        "https://www.googleapis.com/auth/apps.groups.settings",
    ]

    creds = service_account.Credentials.from_service_account_file(
        args.sa_creds, scopes=SCOPES, subject=args.sa_delegate
    )

    svc = discovery.build(
        "admin", "directory_v1", credentials=creds, cache_discovery=False
    )
    try:
        logging.info(f"Creating group {ggcfg['email']}")
        svc.groups().insert(
            body={
                "description": ggcfg["description"],
                "email": ggcfg["email"],
                "name": ggcfg["name"],
            }
        ).execute()
    except HttpError as e:
        if e.status_code == 409:  # entity already exists
            logging.info("Group already exists")
        else:
            raise
    finally:
        svc.close()

    svc = discovery.build(
        "groupssettings", "v1", credentials=creds, cache_discovery=False
    )
    try:
        logging.info(f"Configuring group {ggcfg['email']}")
        svc.groups().patch(
            groupUniqueId=ggcfg["email"],
            body=ggcfg,
        ).execute()
    finally:
        svc.close()

    svc = discovery.build(
        "admin", "directory_v1", credentials=creds, cache_discovery=False
    )
    members = svc.members()

    # The flow for populating members and designating managers is a little
    # weird to work-around a Google API bug where members.get() fails sometimes:
    # https://stackoverflow.com/questions/66992809/google-admin-sdk-directory-api-members-get-returns-a-404-for-member-email-but

    for member in mmcfg["digest_members"]:
        if member in args.ignore:
            logging.info(f"Skipping digest member {member} (on the ignore list)")
            continue
        body = {"email": member, "delivery_settings": "DIGEST"}
        if member in mmcfg["owner"]:
            logging.info(f"Inserting digest member {member} (manager)")
            body["role"] = "MANAGER"
        else:
            logging.info(f"Inserting digest member {member}")
        try:
            members.insert(groupKey=ggcfg["email"], body=body).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logging.info(f"User {member} already part of the group")
            else:
                raise

    for member in mmcfg["regular_members"]:
        if member in args.ignore:
            logging.info(f"Skipping member {member} (on the ignore list)")
            continue
        body = {"email": member, "delivery_settings": "ALL_MAIL"}
        if member in mmcfg["owner"]:
            logging.info(f"Inserting member {member} (manager)")
            body["role"] = "MANAGER"
        else:
            logging.info(f"Inserting member {member}")
        try:
            members.insert(groupKey=ggcfg["email"], body=body).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logging.info(f"User {member} already part of the group")
            else:
                raise

    for owner in set(mmcfg["owner"]) - set(
        mmcfg["digest_members"] + mmcfg["regular_members"]
    ):
        if owner in args.ignore:
            logging.info(f"Skipping non-member manager {owner} (on the ignore list)")
            continue
        logging.info(f"Inserting non-member manager {owner}")
        try:
            members.insert(
                groupKey=ggcfg["email"],
                body={"email": owner, "role": "MANAGER", "delivery_settings": "NONE"},
            ).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logging.info(f"User {owner} already part of the group")

    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    for nonmember in mmcfg["accept_these_nonmembers"]:
        if nonmember in args.ignore:
            logging.info(f"Skipping non-member {nonmember} (on the ignore list)")
            continue
        if not re.match(email_regex, nonmember):
            logging.info(f"Ignoring invalid non-member email {nonmember}")
            continue
        logging.info(f"Inserting non-member {nonmember}")
        try:
            members.insert(
                groupKey=ggcfg["email"],
                body={"email": nonmember, "delivery_settings": "NONE"},
            ).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logging.info(f"User {nonmember} already part of the group")

    svc.close()

    logging.info("!!!   SOME GOOGLE GROUP OPTIONS CANNOT BE SET PROGRAMMATICALLY")
    addr, domain = ggcfg["email"].split("@")
    logging.info(
        f"!!!   Configuration URL: https://groups.google.com/u/2/a/{domain}/g/{addr}/settings"
    )
    logging.info(f"!!!   Set 'Subject prefix' to '{mmcfg['subject_prefix'].strip()}'")
    logging.info(f"!!!   Consider enabling 'Include the standard Groups footer'")


if __name__ == "__main__":
    sys.exit(main())
