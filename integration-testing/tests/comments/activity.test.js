/* eslint-env jest */

const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Post owner comment activity does not change newCommentActivity', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.hasNewCommentActivity).toBe(false)

  // we comment on the post
  const commentId = uuidv4()
  variables = {commentId, postId, text: 'lore? ipsum!'}
  resp = await ourClient.mutate({mutation: mutations.addComment, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId)

  // check there is no new comment activity on the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.hasNewCommentActivity).toBe(false)

  // delete the comment
  resp = await ourClient.mutate({mutation: mutations.deleteComment, variables: {commentId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deleteComment.commentId).toBe(commentId)

  // check there is no new comment activity on the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.hasNewCommentActivity).toBe(false)
})

test('Post newCommentActivity - set, reset, privacy', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add a post
  const postId = uuidv4()
  let variables = {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'}
  let resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.hasNewCommentActivity).toBe(false)

  // check they cannot see Post newCommentActivity
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.hasNewCommentActivity).toBeNull()

  // they comment on the post twice
  const commentId1 = uuidv4()
  variables = {commentId: commentId1, postId, text: 'lore? ip!'}
  resp = await theirClient.mutate({mutation: mutations.addComment, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId1)

  const commentId2 = uuidv4()
  variables = {commentId: commentId2, postId, text: 'lore? ip!'}
  resp = await theirClient.mutate({mutation: mutations.addComment, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addComment.commentId).toBe(commentId2)

  // check there is new comment activity on the post, user
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.hasNewCommentActivity).toBe(true)

  // we report to have viewed one comment, the first one
  resp = await ourClient.mutate({mutation: mutations.reportCommentViews, variables: {commentIds: [commentId1]}})
  expect(resp.errors).toBeUndefined()

  // check there is now *no* new comment activity on the post & user
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.hasNewCommentActivity).toBe(false)

  // they delete the comment, the one we haven't viewed
  resp = await theirClient.mutate({mutation: mutations.deleteComment, variables: {commentId: commentId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deleteComment.commentId).toBe(commentId2)

  // check there is new comment activity on the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.hasNewCommentActivity).toBe(true)

  // we report to have viewed comment that was no deleted, again
  resp = await ourClient.mutate({mutation: mutations.reportCommentViews, variables: {commentIds: [commentId1]}})
  expect(resp.errors).toBeUndefined()

  // check there is now *no* new comment activity on the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.hasNewCommentActivity).toBe(false)

  // we delete a comment, the one we viewed
  resp = await ourClient.mutate({mutation: mutations.deleteComment, variables: {commentId: commentId1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deleteComment.commentId).toBe(commentId1)

  // check there is no new comment activity on the post
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.hasNewCommentActivity).toBe(false)
})
