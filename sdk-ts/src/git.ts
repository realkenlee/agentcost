import { execSync } from "child_process";

let _cache: Record<string, string> | null = null;

export function getGitContext(): Record<string, string> {
  if (_cache) return _cache;

  const ctx: Record<string, string> = {};

  // GitHub Actions
  if (process.env.GITHUB_ACTIONS) {
    ctx.ci       = "github";
    ctx.repo     = process.env.GITHUB_REPOSITORY ?? "";
    ctx.user     = process.env.GITHUB_ACTOR ?? "";
    ctx.workflow = process.env.GITHUB_WORKFLOW ?? "";
    ctx.sha      = (process.env.GITHUB_SHA ?? "").slice(0, 8);
    const ref    = process.env.GITHUB_REF ?? "";
    const prMatch = ref.match(/\/pull\/(\d+)\//);
    if (prMatch) ctx.pr = prMatch[1];
    ctx.branch = process.env.GITHUB_HEAD_REF || process.env.GITHUB_REF_NAME || "";
    return (_cache = clean(ctx));
  }

  // GitLab CI
  if (process.env.GITLAB_CI) {
    ctx.ci     = "gitlab";
    ctx.repo   = process.env.CI_PROJECT_PATH ?? "";
    ctx.user   = process.env.GITLAB_USER_LOGIN ?? "";
    ctx.branch = process.env.CI_COMMIT_BRANCH ?? "";
    ctx.pr     = process.env.CI_MERGE_REQUEST_IID ?? "";
    ctx.sha    = process.env.CI_COMMIT_SHORT_SHA ?? "";
    return (_cache = clean(ctx));
  }

  // Local git
  try {
    ctx.branch = git("rev-parse", "--abbrev-ref", "HEAD");
    ctx.sha    = git("rev-parse", "--short", "HEAD");
    ctx.user   = git("config", "user.email");
    const remote = git("remote", "get-url", "origin");
    ctx.repo   = parseRepo(remote);
  } catch { /* not in a git repo */ }

  return (_cache = clean(ctx));
}

function git(...args: string[]): string {
  return execSync(`git ${args.join(" ")}`, { stdio: ["pipe", "pipe", "pipe"] }).toString().trim();
}

function parseRepo(remote: string): string {
  for (const prefix of ["https://github.com/", "git@github.com:", "https://gitlab.com/"]) {
    if (remote.includes(prefix)) return remote.split(prefix)[1].replace(/\.git$/, "");
  }
  return remote;
}

function clean(obj: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v));
}
