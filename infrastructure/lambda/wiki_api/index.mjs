import {
  CodeCommitClient,
  GetFolderCommand,
  GetFileCommand,
  GetBranchCommand,
  ListBranchesCommand,
  GetCommitCommand,
  GetDifferencesCommand,
} from '@aws-sdk/client-codecommit';
import {
  SSMClient,
  GetParametersByPathCommand,
} from '@aws-sdk/client-ssm';

const codecommit = new CodeCommitClient();
const ssm = new SSMClient();

const DEFAULT_BRANCH = process.env.DEFAULT_BRANCH || 'main';

function response(statusCode, body) {
  return {
    statusCode,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

function repoName(wiki) {
  return `wiki-${wiki}`;
}

async function listWikis() {
  const params = [];
  let nextToken;
  do {
    const res = await ssm.send(new GetParametersByPathCommand({
      Path: '/wikis/',
      Recursive: true,
      NextToken: nextToken,
    }));
    for (const p of res.Parameters || []) {
      try {
        params.push(JSON.parse(p.Value));
      } catch {
        params.push({ name: p.Name, value: p.Value });
      }
    }
    nextToken = res.NextToken;
  } while (nextToken);
  return response(200, params);
}

async function getTree(params) {
  if (!params.wiki) return response(400, { error: 'Missing required parameter: wiki' });
  const folderPath = params.path || '/';
  const res = await codecommit.send(new GetFolderCommand({
    repositoryName: repoName(params.wiki),
    folderPath,
  }));
  return response(200, {
    path: res.folderPath,
    files: (res.files || []).map(f => ({ path: f.relativePath, size: f.size })),
    subFolders: (res.subFolders || []).map(f => ({ path: f.relativePath })),
  });
}

async function getFile(params) {
  if (!params.wiki) return response(400, { error: 'Missing required parameter: wiki' });
  if (!params.path) return response(400, { error: 'Missing required parameter: path' });
  const res = await codecommit.send(new GetFileCommand({
    repositoryName: repoName(params.wiki),
    filePath: params.path,
  }));
  const content = new TextDecoder('utf-8').decode(res.fileContent);
  return response(200, {
    path: res.filePath,
    content,
    size: res.fileSize,
  });
}

async function getBranch(params) {
  if (!params.wiki) return response(400, { error: 'Missing required parameter: wiki' });
  const res = await codecommit.send(new GetBranchCommand({
    repositoryName: repoName(params.wiki),
    branchName: DEFAULT_BRANCH,
  }));
  return response(200, {
    branch: res.branch.branchName,
    commitId: res.branch.commitId,
  });
}

async function listBranches(params) {
  if (!params.wiki) return response(400, { error: 'Missing required parameter: wiki' });
  const branches = [];
  let nextToken;
  do {
    const res = await codecommit.send(new ListBranchesCommand({
      repositoryName: repoName(params.wiki),
      nextToken,
    }));
    branches.push(...(res.branches || []));
    nextToken = res.nextToken;
  } while (nextToken);
  return response(200, { branches });
}

async function getCommits(params) {
  if (!params.wiki) return response(400, { error: 'Missing required parameter: wiki' });
  const limit = Math.min(parseInt(params.limit, 10) || 10, 100);
  const branchRes = await codecommit.send(new GetBranchCommand({
    repositoryName: repoName(params.wiki),
    branchName: DEFAULT_BRANCH,
  }));
  const commits = [];
  let commitId = branchRes.branch.commitId;
  while (commitId && commits.length < limit) {
    const commitRes = await codecommit.send(new GetCommitCommand({
      repositoryName: repoName(params.wiki),
      commitId,
    }));
    const c = commitRes.commit;
    commits.push({
      commitId: c.commitId,
      message: c.message,
      author: c.author?.name,
      email: c.author?.email,
      date: c.author?.date,
    });
    commitId = c.parents?.length ? c.parents[0] : null;
  }
  return response(200, commits);
}

async function getDiff(params) {
  if (!params.wiki) return response(400, { error: 'Missing required parameter: wiki' });
  if (!params.from || !params.to) return response(400, { error: 'Missing required parameters: from, to' });
  const entries = [];
  let nextToken;
  do {
    const res = await codecommit.send(new GetDifferencesCommand({
      repositoryName: repoName(params.wiki),
      beforeCommitSpecifier: params.from,
      afterCommitSpecifier: params.to,
      NextToken: nextToken,
    }));
    for (const d of res.differences || []) {
      entries.push({
        changeType: d.changeType,
        beforePath: d.beforeBlob?.path,
        afterPath: d.afterBlob?.path,
      });
    }
    nextToken = res.NextToken;
  } while (nextToken);
  return response(200, entries);
}

export async function handler(event) {
  const path = event.rawPath;
  const params = event.queryStringParameters || {};

  try {
    switch (path) {
      case '/api/wikis':
        return await listWikis();
      case '/api/tree':
        return await getTree(params);
      case '/api/file':
        return await getFile(params);
      case '/api/branch':
        return await getBranch(params);
      case '/api/branches':
        return await listBranches(params);
      case '/api/commits':
        return await getCommits(params);
      case '/api/diff':
        return await getDiff(params);
      default:
        return response(404, { error: 'Not found' });
    }
  } catch (err) {
    if (err.name === 'RepositoryDoesNotExistException') {
      return response(404, { error: 'Repository not found' });
    }
    if (err.name === 'FileDoesNotExistException') {
      return response(404, { error: 'File not found' });
    }
    if (err.name === 'FolderDoesNotExistException') {
      return response(404, { error: 'Folder not found' });
    }
    if (err.name === 'BranchDoesNotExistException') {
      return response(404, { error: 'Branch not found' });
    }
    if (err.name === 'CommitDoesNotExistException') {
      return response(404, { error: 'Commit not found' });
    }
    console.error('Unhandled error:', err);
    return response(500, { error: 'Internal server error' });
  }
}
