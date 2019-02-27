#!/usr/bin/python
import configparser
import datetime
import email
import email.header
import email.mime.text
import imaplib
import os
import re
import smtplib
import sys
from _socket import gaierror
from log import Log

config = None
config_file_path = "autoresponder.config.ini"
incoming_mail_server = None
outgoing_mail_server = None
statistics = {
    "start_time": datetime.datetime.now(),
    "mails_loading_error": 0,
    "mails_total": 0,
    "mails_processed": 0,
    "mails_in_trash": 0,
    "mails_wrong_sender": 0
}


def run():
    get_config_file_path()
    initialize_configuration()
    connect_to_mail_servers()
    check_folder_names()
    mails = fetch_emails()
    Log.d('mails: ' + str(mails))
    for mail in mails:
        process_email(mail)
    log_statistics()
    shutdown(0)


def get_config_file_path():
    if "--help" in sys.argv or "-h" in sys.argv:
        display_help_text()
    if "--config-path" in sys.argv and len(sys.argv) >= 3:
        global config_file_path
        config_file_path = sys.argv[2]
    if not os.path.isfile(config_file_path):
        shutdown_with_error("Configuration file not found. Expected it at '" + config_file_path + "'.")


def initialize_configuration():
    try:
        config_file = configparser.ConfigParser()
        config_file.read(config_file_path, encoding="gb18030")
        global config
        config = {
            'in.user': cast(config_file["login credentials"]["mailserver.incoming.username"], str),
            'in.pw': cast(config_file["login credentials"]["mailserver.incoming.password"], str),
            'out.user': cast(config_file["login credentials"]["mailserver.outgoing.username"], str),
            'out.pw': cast(config_file["login credentials"]["mailserver.outgoing.password"], str),
            'display.name': cast(config_file["login credentials"]["mailserver.outgoing.display.name"], str),
            'display.mail': cast(config_file["login credentials"]["mailserver.outgoing.display.mail"], str),
            'in.host': cast(config_file["mail server settings"]["mailserver.incoming.imap.host"], str),
            'in.port': cast(config_file["mail server settings"]["mailserver.incoming.imap.port.ssl"], str),
            'out.host': cast(config_file["mail server settings"]["mailserver.outgoing.smtp.host"], str),
            'out.port': cast(config_file["mail server settings"]["mailserver.outgoing.smtp.port.tls"], str),
            'folders.inbox': cast(config_file["mail server settings"]["mailserver.incoming.folders.inbox.name"], str),
            'folders.trash': cast(config_file["mail server settings"]["mailserver.incoming.folders.trash.name"], str),
            'request.from': cast(config_file["mail content settings"]["mail.request.from"], str),
            'reply.subject': cast(config_file["mail content settings"]["mail.reply.subject"], str).strip(),
            'reply.body': cast(config_file["mail content settings"]["mail.reply.body"], str).strip()
        }
    except KeyError as e:
        shutdown_with_error("Configuration file is invalid! (Key not found: " + str(e) + ")")


def connect_to_mail_servers():
    connect_to_imap()
    connect_to_smtp()


def check_folder_names():
    (retcode, msg_count) = incoming_mail_server.select(config['folders.inbox'])
    if retcode != "OK":
        shutdown_with_error("Inbox folder does not exist: " + config['folders.inbox'])
    Log.i('INBOX mails have gotten.')
    Log.d('msg_count: ' + str(msg_count))
    (retcode, msg_count) = incoming_mail_server.select(config['folders.trash'])
    if retcode != "OK":
        shutdown_with_error("Trash folder does not exist: " + config['folders.trash'])
    Log.i('TRASH mails have gotten.')
    Log.d('msg_count: ' + str(msg_count))


def connect_to_imap():
    try:
        do_connect_to_imap()
    except gaierror:
        shutdown_with_error("IMAP connection failed! Specified host not found.")
    except imaplib.IMAP4_SSL.error as e:
        shutdown_with_error("IMAP login failed! Reason: '" + cast(e.args[0], str, 'gb18030') + "'.")
    except Exception as e:
        shutdown_with_error("IMAP connection/login failed! Reason: '" + cast(e, str) + "'.")


def do_connect_to_imap():
    global incoming_mail_server
    incoming_mail_server = imaplib.IMAP4_SSL(config['in.host'], config['in.port'])
    (retcode, capabilities) = incoming_mail_server.login(config['in.user'], config['in.pw'])
    if retcode != "OK":
        shutdown_with_error("IMAP login failed! Return code: '" + cast(retcode, str) + "'.")
    Log.i('IMAP login succeed.')


def connect_to_smtp():
    try:
        do_connect_to_smtp()
    except gaierror:
        shutdown_with_error("SMTP connection failed! Specified host not found.")
    except smtplib.SMTPAuthenticationError as e:
        shutdown_with_error("SMTP login failed! Reason: '" + cast(e.smtp_error, str, 'gb18030') + "'.")
    except Exception as e:
        shutdown_with_error("SMTP connection/login failed! Reason: '" + cast(e, str) + "'.")


def do_connect_to_smtp():
    global outgoing_mail_server
    outgoing_mail_server = smtplib.SMTP_SSL(config['out.host'], config['out.port'])
    #outgoing_mail_server.starttls()
    (retcode, capabilities) = outgoing_mail_server.login(config['out.user'], config['out.pw'])
    if not (retcode == 235 or retcode == 250):
        shutdown_with_error("SMTP login failed! Return code: '" + str(retcode) + "'.")
    Log.i('SMTP login succeed.')


def fetch_emails():
    # get the message ids from the inbox folder
    incoming_mail_server.select(config['folders.inbox'])
    (retcode, message_indices) = incoming_mail_server.search(None, 'UNSEEN')
    if retcode == 'OK':
        messages = []
        for message_index in message_indices[0].split():
            # get the actual message for the current index
            (retcode, data) = incoming_mail_server.fetch(message_index, '(RFC822)')
            if retcode == 'OK':
                # parse the message into a useful format
                message = email.message_from_string(data[0][1].decode('gb18030'))
                (retcode, data) = incoming_mail_server.fetch(message_index, "(UID)")
                if retcode == 'OK':
                    mail_uid = parse_uid(cast(data[0], str, 'gb18030'))
                    message['mailserver_email_uid'] = mail_uid
                    messages.append(message)
                else:
                    statistics['mails_loading_error'] += 1
                    log_warning("Failed to get UID for email with index '" + message_index + "'.")
            else:
                statistics['mails_loading_error'] += 1
                log_warning("Failed to get email with index '" + message_index + "'.")
        statistics['mails_total'] = len(messages)
        return messages
    else:
        return []


def process_email(mail):
    try:
        mail_from = email.header.decode_header(mail['From'])
        mail_sender = mail_from[-1]
        mail_sender = cast(mail_sender[0], str, 'gb18030')
        if config['request.from'] in mail_sender:
            reply_to_email(mail)
            delete_email(mail)
        else:
            statistics['mails_wrong_sender'] += 1
        statistics['mails_processed'] += 1
    except Exception as e:
        Log.w("Unexpected error while processing email: '" + str(e) + "'.")


def reply_to_email(mail):
    Log.d('mail: ' + str(mail))
    #receiver_email = email.header.decode_header(mail['Reply-To'])[0][0]
    receiver_email = re.search(r'<.*?>', mail['From'], re.I|re.M)[0][1:-1]  # "@#$%^&*(" <xxx@xxx.com>
    Log.d('mail[From]: ' + receiver_email)
    message = email.mime.text.MIMEText(config['reply.body'])
    message['Subject'] = config['reply.subject']
    message['To'] = receiver_email
    message['From'] = email.utils.formataddr((
        cast(email.header.Header(config['display.name'], 'gb18030'), str), config['display.mail']))
    outgoing_mail_server.sendmail(config['display.mail'], receiver_email, message.as_string())
    Log.i('Reply mail to ' + receiver_email + '.')

def delete_email(mail):
    result = incoming_mail_server.uid('COPY', mail['mailserver_email_uid'], config['folders.trash'])
    if result[0] == "OK":
        statistics['mails_in_trash'] += 1
    else:
        log_warning("Copying email to trash failed. Reason: " + str(result))
    incoming_mail_server.uid('STORE', mail['mailserver_email_uid'], '+FLAGS', '(\Delete)')
    incoming_mail_server.expunge()
    Log.i('Mail has been seen.')


def parse_uid(data):
    pattern_uid = re.compile('\d+ \(UID (?P<uid>\d+)\)')
    match = pattern_uid.match(data)
    return match.group('uid')


def cast(obj, to_type, options=None):
    try:
        if options is None:
            return to_type(obj)
        else:
            return to_type(obj, options)
    except ValueError and TypeError:
        return obj


def shutdown_with_error(message):
    message = "Error! " + str(message)
    message += "\nCurrent configuration file path: '" + str(config_file_path) + "'."
    if config is not None:
        message += "\nCurrent configuration: " + str(config)
    Log.e(print(message))
    shutdown(-1)


def log_warning(message):
    Log.w("Warning! " + message)


def log_statistics():
    run_time = datetime.datetime.now() - statistics['start_time']
    total_mails = statistics['mails_total']
    loading_errors = statistics['mails_loading_error']
    wrong_sender_count = statistics['mails_wrong_sender']
    processing_errors = total_mails - statistics['mails_processed']
    moving_errors = statistics['mails_processed'] - statistics['mails_in_trash'] - statistics['mails_wrong_sender']
    total_warnings = loading_errors + processing_errors + moving_errors
    message = "Executed "
    message += "without warnings " if total_warnings is 0 else "with " + str(total_warnings) + " warnings "
    message += "in " + str(run_time.total_seconds()) + " seconds. "
    message += "Found " + str(total_mails) + " emails in inbox"
    message += ". " if wrong_sender_count is 0 else " with " + str(wrong_sender_count) + " emails from wrong senders. "
    message += "Processed " + str(statistics['mails_processed']) + \
               " emails, replied to " + str(total_mails - wrong_sender_count) + " emails. "
    if total_warnings is not 0:
        message += "Encountered " + str(loading_errors) + " errors while loading emails, " + \
                   str(processing_errors) + " errors while processing emails and " + \
                   str(moving_errors) + " errors while moving emails to trash."
    Log.i(message)


def display_help_text():
    print("Options:")
    print("\t--help: Display this help information")
    print("\t--config-path <path/to/config/file>: "
          "Override path to config file (defaults to same directory as the script is)")
    exit(0)


def shutdown(error_code):
    if incoming_mail_server is not None:
        try:
            incoming_mail_server.close()
        except Exception:
            pass
        try:
            incoming_mail_server.logout()
        except Exception:
            pass
    if outgoing_mail_server is not None:
        try:
            outgoing_mail_server.quit()
        except Exception:
            pass
    exit(error_code)


run()
