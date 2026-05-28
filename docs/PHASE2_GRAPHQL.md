# Phase 2: GraphQL Migration Plan

Current data collection uses the GitHub REST API v3. Several high-value signals
are limited or unreliable with REST. This document captures the migration plan
so the path is preserved without blocking Phase 1 shipping.

## Why GraphQL?

| Problem (REST) | GraphQL solution |
|----------------|-----------------|
| `commit.author.date` diverges from `pushed_at` due to rebases → weak backdating signal | `pushedDate` on `Commit` node is set by GitHub at push time, cryptographically tamper-proof |
| Commit history capped at `github_commits_per_repo` per repo → false inactivity | `defaultBranchRef.target.history` returns full history with cursor pagination |
| PR review count requires a separate search API call (`type:pr reviewed-by:X`) with a tight rate limit (30/min authenticated) | `pullRequests(states:[OPEN,MERGED]) { reviews(first:1) }` on user contributions returns structured data |
| Contributor data requires one API call per repo | `Repository.collaborators` in one query |

## Scope

Replace `app/services/github_client.py` fetch methods with GraphQL equivalents.
Signal code in `app/services/analysis_service.py` consumes enriched `GitHubCommit`
and `CollaborationCounts` models — **those contracts stay the same**, so signal
code won't need to change.

## New / Changed Endpoints

### User activity query (replaces `fetch_repos` + `fetch_commits`)
```graphql
query UserActivity($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 30, orderBy: {field: PUSHED_AT, direction: DESC}, after: $cursor) {
      pageInfo { endCursor hasNextPage }
      nodes {
        name stars:stargazerCount forks:forkCount primaryLanguage { name }
        pushedAt updatedAt description repositoryTopics(first:10) { nodes { topic { name } } }
        isFork
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 20) {
                nodes {
                  oid committedDate pushedDate
                  author { user { login } email date }
                  additions deletions
                  changedFilesIfAvailable
                  messageHeadline
                }
              }
            }
          }
        }
      }
    }
  }
}
```

### Collaboration counts query (replaces `fetch_user_collaboration_counts`)
```graphql
query CollabCounts($login: String!) {
  user(login: $login) {
    contributionsCollection {
      pullRequestContributions { totalCount }
      pullRequestReviewContributions { totalCount }
    }
    issues(states: OPEN) { totalCount }
    closedIssues: issues(states: CLOSED) { totalCount }
  }
}
```

## Migration Strategy

1. Add `GitHubGraphQLClient` class alongside `GitHubClient` (no deletion yet).
2. Gate on `USE_GRAPHQL=false` config flag. When `true`, `PipelineWorker` uses the
   GraphQL client; otherwise falls back to REST.
3. Port signal tests to run against both clients (parameterized fixture).
4. Once GraphQL client reaches signal-parity in CI, flip the default to `true`.
5. Delete `GitHubClient` REST methods that are superseded.

## Authentication

GraphQL v4 requires an OAuth token (no anonymous access). Gate the GraphQL path
behind `include_private=true` or a `GITHUB_TOKEN` being set. Unauthenticated
analyses continue to use REST.

## Rate Limit Considerations

GraphQL uses a node-cost model (5,000 points/hour authenticated). A typical
analysis query costs ~50–100 points vs ~40 REST calls. This is significantly
better rate-limit efficiency for authenticated users.

## Files to Create

| File | Purpose |
|------|---------|
| `app/services/github_graphql_client.py` | GraphQL client with cursor pagination |
| `tests/test_github_graphql_client.py` | Unit tests with mocked responses |
| `docs/graphql_queries/` | `.graphql` query files for reference |

## Not in Scope

- Changing `contracts.py` models (enrichment is already forward-compatible).
- Changing `analysis_service.py` signal logic.
- Changing any eval code.
