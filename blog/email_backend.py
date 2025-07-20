import ssl

from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend
from django.utils.functional import cached_property


class SMTPSSLBackend(SMTPEmailBackend):
    """Use a compatible TLS context for implicit-SSL SMTP providers."""

    @cached_property
    def ssl_context(self):
        if self.ssl_certfile or self.ssl_keyfile:
            context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
            context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)
        else:
            context = ssl.create_default_context()

        # request OpenSSL's compatible default cipher set, because some
        # implicit-SSL providers reject the narrower Windows Python defaults
        context.set_ciphers("DEFAULT")
        return context


# keep the old import path valid for existing deployments
AlibabaSMTPBackend = SMTPSSLBackend
