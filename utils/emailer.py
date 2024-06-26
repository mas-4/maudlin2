import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.utils.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SMTPWrapper(smtplib.SMTP_SSL):
    """
    A wrapper for handling SMTP connections to fastmail, other servers.

    From https://alexwlchan.net/2016/05/python-smtplib-and-fastmail/
    """

    def __init__(self, url, username, password):
        super().__init__(url, port=465)
        self.login(username, password)

    def send_mail(self,
                  *,
                  from_addr: str,
                  to_addrs: list[str],
                  msg: str,
                  subject: str,
                  attachments=None):
        msg_root = MIMEMultipart()
        msg_root['Subject'] = subject
        msg_root['From'] = from_addr
        msg_root['To'] = ', '.join(to_addrs)

        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)
        msg_alternative.attach(MIMEText(msg))  # noqa

        if attachments:
            for attachment in attachments:
                prt = MIMEBase('application', "octet-stream")
                prt.set_payload(open(attachment, "rb").read())
                encoders.encode_base64(prt)
                prt.add_header('Content-Disposition', 'attachment; filename="%s"' % attachment.replace('"', ''))
                msg_root.attach(prt)

        self.sendmail(from_addr, to_addrs, msg_root.as_string())


def send_notification(message: str):
    if not Config.emails_to_notify:
        return

    with SMTPWrapper(Config.domain, Config.email, Config.pw) as server:
        server.send_mail(from_addr=Config.email, to_addrs=Config.emails, msg=message, subject="Maudlin Daily Report")

