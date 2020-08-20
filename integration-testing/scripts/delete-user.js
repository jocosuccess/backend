#!/usr/bin/env node

const AWS = require('aws-sdk')
const AWSAppSyncClient = require('aws-appsync').default
const dotenv = require('dotenv')
const fs = require('fs')
const gql = require('graphql-tag')
require('isomorphic-fetch')

dotenv.config()
AWS.config = new AWS.Config()

const appsyncApiUrl = process.env.APPSYNC_GRAPHQL_URL
if (appsyncApiUrl === undefined) throw new Error('Env var APPSYNC_GRAPHQL_URL must be defined')

const deleteUserGQL = gql`
  mutation DeleteUser {
    user: deleteUser {
      userId
      username
    }
  }
`

if (process.argv.length !== 3) {
  console.log('Usage: delete-user.js <tokens/credential file generated by sign-user-in-*.js>')
  process.exit(1)
}

const tokensCreds = JSON.parse(fs.readFileSync(process.argv[2]))
const awsCredentials = new AWS.Credentials(
  tokensCreds.credentials.AccessKeyId,
  tokensCreds.credentials.SecretKey,
  tokensCreds.credentials.SessionToken,
)
const appsyncConfig = {
  url: appsyncApiUrl,
  region: AWS.config.region,
  auth: {type: 'AWS_IAM', credentials: awsCredentials},
  disableOffline: true,
}
const appsyncOptions = {
  defaultOptions: {
    query: {
      fetchPolicy: 'network-only',
      errorPolicy: 'all',
    },
  },
}
const appsyncClient = new AWSAppSyncClient(appsyncConfig, appsyncOptions)

// TODO: this should be await'ed
appsyncClient.mutate({mutation: deleteUserGQL}).then(({data: {user: {username}}}) =>
  console.log(`Successfully deleted user '${username}'`),
)
