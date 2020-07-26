import logging

from boto3.dynamodb.conditions import Key

logger = logging.getLogger()


class FeedDynamo:
    def __init__(self, dynamo_client):
        self.client = dynamo_client

    def build_pk(self, feed_user_id, post_id, old_pk=False):
        return (
            {'partitionKey': f'user/{feed_user_id}', 'sortKey': f'feed/{post_id}'}
            if old_pk
            else {'partitionKey': f'post/{post_id}', 'sortKey': f'feed/{feed_user_id}'}
        )

    def parse_pk(self, pk):
        pk_parts = pk['partitionKey'].split('/')
        sk_parts = pk['sortKey'].split('/')
        if pk_parts[0] == 'user':  # old_format
            feed_user_id, post_id = pk_parts[1], sk_parts[1]
        else:
            post_id, feed_user_id = pk_parts[1], sk_parts[1]
        return feed_user_id, post_id

    def build_item(self, feed_user_id, post_item, old_pk=False):
        "Build a feed item for given user's feed"
        posted_by_user_id = post_item['postedByUserId']
        post_id = post_item['postId']
        item = {
            **self.build_pk(feed_user_id, post_id, old_pk=old_pk),
            'schemaVersion': 2,
            'gsiA1PartitionKey': f'feed/{feed_user_id}',
            'gsiA1SortKey': post_item['postedAt'],
            'gsiA2PartitionKey': f'feed/{feed_user_id}',
            'gsiA2SortKey': posted_by_user_id,
            'userId': feed_user_id,
            'postId': post_item['postId'],
            'postedAt': post_item['postedAt'],
            'postedByUserId': posted_by_user_id,
            'gsiK2PartitionKey': f'feed/{feed_user_id}/{posted_by_user_id}',
            'gsiK2SortKey': post_item['postedAt'],
        }
        if old_pk:
            item.pop('gsiA2PartitionKey')
            item.pop('gsiA2SortKey')
        return item

    def add_posts_to_feed(self, feed_user_id, post_item_generator, old_pk=False):
        item_generator = (
            self.build_item(feed_user_id, post_item, old_pk=old_pk) for post_item in post_item_generator
        )
        self.client.batch_put_items(item_generator)

    def add_post_to_feeds(self, feed_user_id_generator, post_item, old_pk=False):
        item_generator = (
            self.build_item(feed_user_id, post_item, old_pk=old_pk) for feed_user_id in feed_user_id_generator
        )
        self.client.batch_put_items(item_generator)

    def delete_by_post_owner(self, feed_user_id, post_user_id):
        "Delete all feed items by `posted_by_user_id` from the feed of `feed_user_id`"
        pk_generator = self.generate_feed_pks_by_posted_by_user(feed_user_id, post_user_id)
        self.client.batch_delete_items(pk_generator)

    # adding an index on post id would allow feed_user_id_generator to be eliminated
    def delete_by_post(self, post_id, feed_user_id_generator):
        "Delete all feed items of `post_id` in the feeds of `feed_user_id_generator`"
        feed_user_ids = list(feed_user_id_generator)  # not ideal, but temporary only needed during migration
        key_generator = (self.build_pk(feed_user_id, post_id) for feed_user_id in feed_user_ids)
        self.client.batch_delete_items(key_generator)
        key_generator = (self.build_pk(feed_user_id, post_id, old_pk=True) for feed_user_id in feed_user_ids)
        self.client.batch_delete_items(key_generator)

    def generate_feed(self, feed_user_id):
        query_kwargs = {
            'KeyConditionExpression': Key('gsiA1PartitionKey').eq(f'feed/{feed_user_id}'),
            'IndexName': 'GSI-A1',
        }
        return self.client.generate_all_query(query_kwargs)

    def generate_feed_pks_by_posted_by_user(self, feed_user_id, posted_by_user_id):
        query_kwargs = {
            'KeyConditionExpression': (Key('gsiK2PartitionKey').eq(f'feed/{feed_user_id}/{posted_by_user_id}')),
            'IndexName': 'GSI-K2',
            'ProjectionExpression': 'partitionKey, sortKey',
        }
        return self.client.generate_all_query(query_kwargs)
