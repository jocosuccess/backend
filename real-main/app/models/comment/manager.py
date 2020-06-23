import collections
import logging

import pendulum

from app import models
from app.mixins.base import ManagerBase
from app.mixins.flag.manager import FlagManagerMixin
from app.mixins.view.manager import ViewManagerMixin

from . import exceptions
from .dynamo import CommentDynamo
from .model import Comment

logger = logging.getLogger()


class CommentManager(FlagManagerMixin, ViewManagerMixin, ManagerBase):

    exceptions = exceptions
    item_type = 'comment'

    def __init__(self, clients, managers=None):
        super().__init__(clients, managers=managers)
        managers = managers or {}
        managers['comment'] = self
        self.block_manager = managers.get('block') or models.BlockManager(clients, managers=managers)
        self.follow_manager = managers.get('follow') or models.FollowManager(clients, managers=managers)
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        if 'dynamo' in clients:
            self.dynamo = CommentDynamo(clients['dynamo'])

    def get_model(self, item_id):
        return self.get_comment(item_id)

    def get_comment(self, comment_id):
        comment_item = self.dynamo.get_comment(comment_id)
        return self.init_comment(comment_item) if comment_item else None

    def init_comment(self, comment_item):
        kwargs = {
            'dynamo': getattr(self, 'dynamo', None),
            'flag_dynamo': getattr(self, 'flag_dynamo', None),
            'view_dynamo': getattr(self, 'view_dynamo', None),
            'block_manager': self.block_manager,
            'follow_manager': self.follow_manager,
            'post_manager': self.post_manager,
            'user_manager': self.user_manager,
        }
        return Comment(comment_item, **kwargs)

    def add_comment(self, comment_id, post_id, user_id, text, now=None):
        now = now or pendulum.now('utc')

        post = self.post_manager.get_post(post_id)
        if not post:
            raise exceptions.CommentException(f'Post `{post_id}` does not exist')

        if post.item.get('commentsDisabled', False):
            raise exceptions.CommentException(f'Comments are disabled on post `{post_id}`')

        if user_id != post.user_id:

            # can't comment if there's a blocking relationship, either direction
            if self.block_manager.is_blocked(post.user_id, user_id):
                raise exceptions.CommentException(f'Post owner `{post.user_id}` has blocked user `{user_id}`')
            if self.block_manager.is_blocked(user_id, post.user_id):
                raise exceptions.CommentException(f'User `{user_id}` has blocked post owner `{post.user_id}`')

            # if post owner is private, must be a follower to comment
            poster = self.user_manager.get_user(post.user_id)
            if poster.item['privacyStatus'] == poster.enums.UserPrivacyStatus.PRIVATE:
                follow = self.follow_manager.get_follow(user_id, post.user_id)
                if not follow or follow.status != follow.enums.FollowStatus.FOLLOWING:
                    msg = f'Post owner `{post.user_id}` is private and user `{user_id}` is not a follower'
                    raise exceptions.CommentException(msg)

        text_tags = self.user_manager.get_text_tags(text)
        transacts = [
            self.dynamo.transact_add_comment(comment_id, post_id, user_id, text, text_tags, commented_at=now),
            self.post_manager.dynamo.transact_increment_comment_count(
                post_id, include_comments_unviewed_count=(user_id != post.user_id),
            ),
            self.user_manager.dynamo.transact_comment_added(user_id),
        ]
        transact_exceptions = [
            exceptions.CommentException(f'Unable to add comment with id `{comment_id}`... id already used?'),
            exceptions.CommentException('Unable to increment Post.commentCount'),
            exceptions.CommentException('Unable to increment User.commentCount'),
        ]
        self.dynamo.client.transact_write_items(transacts, transact_exceptions)

        # if this comment is from anyone other than post owner, count it as new comment activity
        if user_id != post.user_id:
            post.register_new_comment_activity(now=now)

        comment_item = self.dynamo.get_comment(comment_id, strongly_consistent=True)
        return self.init_comment(comment_item)

    def record_views(self, comment_ids, user_id, viewed_at=None):
        grouped_comment_ids = dict(collections.Counter(comment_ids))
        if not grouped_comment_ids:
            return

        post_ids = set()
        for comment_id, view_count in grouped_comment_ids.items():
            comment = self.get_comment(comment_id)
            if not comment:
                logger.warning(f'Cannot record view(s) by user `{user_id}` on DNE comment `{comment_id}`')
                continue
            was_recorded = comment.record_view_count(user_id, view_count, viewed_at=viewed_at)
            if was_recorded:
                post_ids.add(comment.post_id)

        for post_id in post_ids:
            post = self.post_manager.get_post(comment.post_id)
            if user_id == post.user_id:
                post.clear_new_comment_activity()

    def delete_all_by_user(self, user_id):
        for comment_item in self.dynamo.generate_by_user(user_id):
            self.init_comment(comment_item).delete()

    def delete_all_on_post(self, post_id):
        for comment_item in self.dynamo.generate_by_post(post_id):
            self.init_comment(comment_item).delete()
