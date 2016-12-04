# -*- coding: utf-8 -*-
"""Define all controllers/handlers for the app."""

import logging

from models import db, Post, PostLikes, PostComments, User
from support import viewer, helpers, config, slugify, webapp2, time

from webapp2_extras import auth
from webapp2_extras import sessions

from webapp2_extras.auth import InvalidAuthIdError
from webapp2_extras.auth import InvalidPasswordError


def user_required(handler):
    """Decorator that checks if there's a user login."""
    def check_login(self, *args, **kwargs):
        """Redirect user too login page if not login."""
        auth = self.auth
        if not auth.get_user_by_session():
            self.redirect(self.uri_for('auth.login'), abort=True)
        else:
            return handler(self, *args, **kwargs)
    return check_login


class Controller(webapp2.RequestHandler):
    """Base Controller functionality we need to reuse."""

    @webapp2.cached_property
    def auth(self):
        """Shortcut to access the auth instance as a property."""
        return auth.get_auth()

    @webapp2.cached_property
    def user_info(self):
        """Shortcut to access a subset of the user attributes that are stored.

        in the session.
        The list of attributes to store in the session is specified in
          config['webapp2_extras.auth']['user_attributes'].
        :returns
          A dictionary with most user information
        """
        return self.auth.get_user_by_session()

    @webapp2.cached_property
    def user(self):
        """Shortcut to access the current logged in user.

        Unlike user_info, it fetches information from the persistence layer and
        returns an instance of the underlying model.
        :returns
            The instance of the user model associated to the logged in user.
        """
        u = self.user_info
        return User.get_by_id(u['user_id']) if u else None

    def write(self, *a, **kw):
        """Send response to the browser."""
        self.response.out.write(*a, **kw)

    def view(self, template, **params):
        """Render template with given varibles."""
        view = viewer.get_template(template)
        self.write(view.render(params, messages=self.flash_messages, curent_user=self.user))

    def dispatch(self):
        """Get a session store for this request."""
        self.session_store = sessions.get_store(request=self.request)
        try:
            # Dispatch the request.
            webapp2.RequestHandler.dispatch(self)
        finally:
            # Save all sessions.
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        """Return a session using the default cookie key."""
        return self.session_store.get_session()

    @webapp2.cached_property
    def flash_messages(self):
        """Implement flash messages."""
        return self.session.get_flashes(key='_messages')

    def flash(self, message, level='warning'):
        """Flash message."""
        self.session.add_flash(message, level, key='_messages')

    def set_secure_cookie(self, name, val):
        """Set secure cookie."""
        cookie_val = helpers.make_secure_value(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        """Read secure cookie."""
        cookie_val = self.request.cookies.get(name)
        return cookie_val and helpers.check_secure_value(cookie_val)


class HomeIndex(Controller):
    """Home Controller."""

    @user_required
    def get(self):
        """Display most reacent posts."""
        posts = Post.query().order(-Post.created_at).fetch(10)
        self.view('home.html', posts=posts)
        return


class PostIndex(Controller):
    """Base controller for posts."""

    @user_required
    def get(self, id, slug=None):
        """Display existing post."""
        post = self.get_post_by_id(id)
        # We cannot find post in the database...
        if not post:
            self.error(404)
            return
        # If no slug redirect to the full slug url...
        if not slug:
            self.redirect(self.uri_for('post', id=int(id), slug=post.slug))
        # Let display the post...
        self.view('post.html', post=post)

    def get_post_by_id(self, post_id):
        """Commonly used function to retrive post by id."""
        return Post.get_by_id(int(post_id))


class PostNew(PostIndex):
    """Create new post."""

    @user_required
    def get(self):
        """Get the new post form."""
        self.view('post.edit.html', post=())
        return

    @user_required
    def post(self):
        """Save new Post to the database."""
        p = {
            "title": self.request.get('title').strip(),
            "slug": slugify(self.request.get('title')),
            "ribbon": self.request.get('ribbon'),
            "markdown": self.request.get('markdown').strip(),
            "content": self.request.get('content').strip()
        }
        try:  # Try saving the post
            post = Post(ribbon=p["ribbon"], markdown=p["markdown"],
                        user=self.user, title=p[
                            "title"], content=p["content"],
                        slug=p["slug"])
            post.put()
        except Exception, error:
            self.flash(str(error), 'error')
            self.view('post.edit.html', post=p)
            return
        self.flash('Well done my friend! Post: %s was Saved.'
                   % post.title, 'success')
        # Redirect to the new post page
        self.redirect(self.uri_for('post', id=post.key.id(), slug=post.slug))
        return


class PostEdit(PostNew):
    """Update existing post."""

    @user_required
    def get(self, id):
        """Open edit form for the the post."""
        post = self.get_post_by_id(id)
        if not post:
            self.error(404)
            return
        if post.check_author(self.user):
            self.view('post.edit.html', post=post)
            return
        else:
            self.flash('You cannot edit post: %s' % post.title, 'error')
            self.redirect(self.uri_for('blog'))
            return
        

    @user_required
    def post(self, id):
        """Submit the eddited post."""
        post = self.get_post_by_id(id)
        if not post:
            self.error(404)
            return
        if post.check_author(self.user):
            post.title = self.request.get('title').strip()
            post.slug = slugify(post.title).strip()
            post.ribbon = self.request.get('ribbon').strip()
            post.markdown = self.request.get('markdown').strip()
            post.content = self.request.get('content').strip()
            post.put()
            self.flash('Well done my friend! Post: %s was Updated.'
                       % (post.title), 'success')
        else:
            self.flash('You cannot edit post: %s' % post.title, 'error')
        self.redirect(self.uri_for('post', id=post.key.id(), slug=post.slug))
        return


class PostDelete(PostIndex):
    """Delete existing post."""

    @user_required
    def get(self, id):
        """delete a post.

        Todo:
            * Move in post method.
        """
        post = self.get_post_by_id(id)
        if post.check_author(self.user):
            post.key.delete()
            self.flash('Post: %s was Deleted.' % post.title, 'warning')
            time.sleep(0.5)
        else:
            self.flash('You cannot delete post: %s' % post.title, 'error')
        self.redirect(self.uri_for('blog'))
        return


class PostLike(PostIndex):
    """Like a post."""

    @user_required
    def get(self, id):
        post = self.get_post_by_id(id)
        if post.liked_by(self.user):
            self.flash('You have liked this already.', 'warning')
        elif post.check_author(self.user):
            self.flash('You cannot like your post\'s.', 'error')
        else:
            PostLikes(post=post.key, user=self.user.key).put()
            self.flash('Thank you for your like.', 'success')
            time.sleep(0.5)
            
        self.redirect(self.uri_for('post', id=post.key.id(), slug=post.slug))
        return

class PostComment(PostIndex):
    """Comment on post."""

    @user_required
    def post(self, id):
        post = self.get_post_by_id(id)
        comment = self.request.get('comment').strip()
        if comment:
            PostComments(post=post.key, user=self.user, 
                comment=comment).put()
            self.flash('Thank you for your comment.', 'success')
            time.sleep(0.5)
        else: 
            self.flash('You cannot submit empty comment', 'error')
        self.redirect(self.uri_for('post', id=post.key.id(), slug=post.slug))
        return


class AuthIndex(Controller):
    """Base controller for Auth functionality."""

    def valid_username(self, username):
        """Check if the username is valid."""
        return username and config.REGEXR_USERNAME.match(username)

    def valid_password(self, password):
        """Check if the password is valid."""
        return password and config.REGEXR_PASSWORD.match(password)

    def valid_email(self, email):
        """Check if the email is valid."""
        return not email or config.REGEXR_EMAIL.match(email)


class UserRegisterIndex(AuthIndex):
    """Register page."""

    def get(self):
        """Display register form."""
        self.view('register.html')

    def post(self):
        """Try to save the new user."""
        valid = True
        username = self.request.get('username').strip()
        email = self.request.get('email').strip()
        password = self.request.get('password').strip()
        re_password = self.request.get('password-validate').strip()
        params = dict(username=username, email=email)
        if not self.valid_username(username):
            params['error_username'] = "That's not a valid username."
            valid = None
        if not self.valid_password(password):
            params['error_password'] = "That wasn't a valid password."
            valid = None
        elif password != re_password:
            params['error_password_verify'] = "Your passwords didn't match."
            valid = None

        if not self.valid_email(email):
            params['error_email'] = "That's not a valid email."
            valid = None

        if valid:
            uniques = ['email_address']
            success, info = User.create_user(username, uniques,
                                             email_address=email,
                                             name=username,
                                             password_raw=password,
                                             verified=False)
            if not success:
                if 'auth_id' in info:
                    params['error_username'] = "Username already taken."
                    valid = None
                if 'email_address' in info:
                    params['error_email'] = "That E-mail address is in use."
                    valid = None
        if not valid:
            self.view('register.html', **params)
        else:
            user_id = info.get_id()
            token = User.create_signup_token(user_id)
            verification_url = self.uri_for('auth.verification', operation='v',
                                            user_id=user_id, token=token,
                                            _full=True)
            self.view('verification.html', username=username,
                      verification_url=verification_url)


class UserLoginIndex(AuthIndex):
    """Login page."""

    def get(self):
        """Show login form."""
        self.view('login.html')

    def post(self):
        """Try to login the user."""
        username = self.request.get('username')
        password = self.request.get('password')
        try:
            u = self.auth.get_user_by_password(
                username, password, remember=True, save_session=True)
            self.redirect(self.uri_for('blog'))
        except (InvalidAuthIdError, InvalidPasswordError) as e:
            self.flash('Login failed for user %s because of %s' %
                       (username, type(e)), 'error')
            self.redirect(self.uri_for('auth.login'))


class UserLogoutIndex(AuthIndex):
    """Logout page."""

    def get(self):
        """Destroy user sesion."""
        self.auth.unset_session()
        self.redirect(self.uri_for('auth.login'))


class UserVerification(AuthIndex):
    """Email Verification page."""

    def get(self, *args, **kwargs):
        """Validate user email address."""
        user = None
        user_id = kwargs['user_id']
        signup_token = kwargs['token']
        verification_type = kwargs['operation']
        # it should be something more concise like
        # self.auth.get_user_by_token(user_id, signup_token)
        # unfortunately the auth interface does not (yet) allow to manipulate
        # signup tokens concisely
        user, ts = User.get_by_auth_token(int(user_id), signup_token, 'signup')
        if not user:
            self.abort(404)

        # store user data in the session
        self.auth.set_session(
            self.auth.store.user_to_dict(user), remember=True)

        if verification_type == 'v':
            # remove signup token, we don't want users to come back with an old
            # link
            User.delete_signup_token(user.get_id(), signup_token)
        if not user.verified:
            user.verified = True
            user.put()
            self.flash('Great %s you can now enjoy the blog.' %
                       user.name, 'success')
            self.redirect(self.uri_for('blog'))
            return
        elif verification_type == 'p':
            # supply user to the page
            params = {
                'user': user,
                'token': signup_token
            }
            self.render_template('resetpassword.html', params)
        else:
            self.abort(404)
