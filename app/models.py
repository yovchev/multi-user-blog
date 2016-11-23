# models.py

import webapp2_extras.appengine.auth.models

from google.appengine.ext import ndb

from webapp2_extras import security

from support import time, db, random, config



"""Posts db model."""


class Post(db.Model):
    slug = db.StringProperty()
    ribbon = db.StringProperty()
    title = db.StringProperty(required=True)
    content = db.TextProperty(required=True)
    markdown = db.TextProperty()
    created_at = db.DateTimeProperty(auto_now_add=True)
    updated_at = db.DateTimeProperty(auto_now=True)

    def get_ribbon_style(self):
        if not self.ribbon:
            self.ribbon = random.choice(config.COLOR_PALETTE)
            self.save()

        if self.ribbon[:1] is "#":
            return 'style="background-color: %s;"' % self.ribbon
        else:
            return 'style="background: url(%s) center / cover;"' % self.ribbon

"""Users db model."""

class User(webapp2_extras.appengine.auth.models.User):
    def set_password(self, raw_password):
        """Sets the password for the current user
        :param raw_password:
            The raw password which will be hashed and stored
        """
        self.password = security.generate_password_hash(raw_password, length=12)

    @classmethod
    def get_by_auth_token(cls, user_id, token, subject='auth'):
        """Returns a user object based on a user ID and token.
        :param user_id:
            The user_id of the requesting user.
        :param token:
            The token string to be verified.
        :returns:
            A tuple ``(User, timestamp)``, with a user object and
            the token timestamp, or ``(None, None)`` if both were not found.
        """
        token_key = cls.token_model.get_key(user_id, subject, token)
        user_key = ndb.Key(cls, user_id)
        # Use get_multi() to save a RPC call.
        valid_token, user = ndb.get_multi([token_key, user_key])
        if valid_token and user:
            timestamp = int(time.mktime(valid_token.created.timetuple()))
            return user, timestamp

        return None, None