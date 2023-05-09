#!/usr/bin/env python
import argparse
import pickle
import sys
from pprint import pprint


def main():
    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('args', nargs='*')
    args = parser.parse_args()
    pprint(args)

    mmcfg = pickle.load(open('gitignore/ara-c.pkl', 'rb'))

    # https://developers.google.com/admin-sdk/groups-settings/v1/reference/groups#json
    if mmcfg['advertised'] and mmcfg['archive']:
        if mmcfg['archive_private']:
            whoCanViewGroup = 'ALL_MEMBERS_CAN_VIEW'
        else:
            whoCanViewGroup = 'ALL_IN_DOMAIN_CAN_VIEW'
    else: # not advertised or not archived
        whoCanViewGroup = 'ALL_MANAGERS_CAN_VIEW'

    if mmcfg['generic_nonmember_action'] in (0, 1):  # accept, hold
        whoCanPostMessage = 'ANYONE_CAN_POST'
    else:  # reject, discard
        whoCanPostMessage = 'ALL_MEMBERS_CAN_POST'
    if mmcfg['default_member_moderation'] and mmcfg['member_moderation_action'] != 0:  # hold
        whoCanPostMessage = 'NONE_CAN_POST'

    if mmcfg['generic_nonmember_action'] == 0:  # accept
        messageModerationLevel = 'MODERATE_NONE'
    else:  # hold, reject, discard
        messageModerationLevel = 'MODERATE_NON_MEMBERS'
    if mmcfg['default_member_moderation']:
        messageModerationLevel = 'MODERATE_ALL_MESSAGES'

    ggcfg = {#"email": mmcfg["email"],
             "name": mmcfg["real_name"],
             "description": mmcfg["description"]+b"\n"+mmcfg['info'] if mmcfg['info'] else mmcfg["description"],
             "whoCanJoin": "CAN_REQUEST_TO_JOIN",
             "whoCanViewMembership": "ALL_IN_DOMAIN_CAN_VIEW",
             "whoCanViewGroup": whoCanViewGroup,
             "allowExternalMembers": "true",  # tighten later
             "whoCanPostMessage": whoCanPostMessage,
             "allowWebPosting": "true",
             "primaryLanguage": "en",
             "isArchived": "true" if mmcfg['archive'] else "false",
             "archiveOnly": "false",
             "messageModerationLevel": messageModerationLevel,
             "spamModerationLevel": "MODERATE",  # this is the default
             "replyTo": "REPLY_TO_IGNORE",  # users individually decide where the message reply is sent.
             # "customReplyTo": "",  # only if replyTo is REPLY_TO_CUSTOM
             "includeCustomFooter": "false",
             # "customFooterText": ""  # only if includeCustomFooter,
             "sendMessageDenyNotification": "false",  # to not have to set defaultMessageDenyNotificationText
             # "defaultMessageDenyNotificationText": "",
             "membersCanPostAsTheGroup": "false",
             "includeInGlobalAddressList": "false",  # has to do with Outlook integration
             "whoCanLeaveGroup": "ALL_MEMBERS_CAN_LEAVE" if mmcfg['unsubscribe_policy'] else 'NONE_CAN_LEAVE',
             "whoCanContactOwner": "ALL_IN_DOMAIN_CAN_CONTACT",
             "favoriteRepliesOnTop": "false",
             "whoCanApproveMembers": "ALL_OWNERS_CAN_APPROVE",  # XXX we want custom role to do this
             "whoCanBanUsers": "OWNERS_AND_MANAGERS",
             "whoCanModerateMembers": "OWNERS_AND_MANAGERS",  # XXX we want custom role to do this
             "whoCanModerateContent": "OWNERS_AND_MANAGERS",  # XXX we want custom role to do this
             "whoCanAssistContent": "NONE",  # has something to do with collaborative inbox
             "enableCollaborativeInbox": "false",
             "whoCanDiscoverGroup": 'ALL_IN_DOMAIN_CAN_DISCOVER' if mmcfg['advertised'] else 'ALL_MEMBERS_CAN_DISCOVER',
             # "defaultSender": "DEFAULT_SELF",  # only matters if posting as group is enabled
    }

    pprint(ggcfg)

if __name__ == '__main__':
    sys.exit(main())

