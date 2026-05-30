# Current Task

**Step**: 1.1 — Remove committed `.env` from git history
**Status**: Starting
**What I'm doing**: Untracking `policyiq/.env` from git, verifying `.gitignore` rules, and addressing the committed credentials
**Blockers/Decisions**: Need to assess whether `git filter-repo` is needed (depends on remote push history)
**Next step**: 1.2 — Replace hard-coded `SECRET_KEY`