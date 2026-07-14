#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.wiki_platform_stack import WikiPlatformStack

app = cdk.App()

# Single stack — deploys the entire wiki platform.
# Individual wikis are created at runtime via POST /api/wikis (no redeploy needed).
WikiPlatformStack(app, "WikiPlatformStack")

app.synth()
