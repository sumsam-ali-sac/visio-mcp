"""AWS CDK: resources from `new Construct(this, 'id')` calls in TypeScript and Python."""

from __future__ import annotations

import re
from pathlib import Path

from ...model import RepoInfo
from ...text import read_text
from ...walk import FileEntry
from ..languages import is_test_path
from .resource import resource


CDK_NEW = re.compile(r"new\s+(?:(\w+)\.)?(\w+)\(\s*(?:this|scope)\s*,\s*['\"]([^'\"]+)['\"]")

CDK_PY = re.compile(r"(\w+)\.(\w+)\(\s*self\s*,\s*['\"]([^'\"]+)['\"]")

CDK_MAP = {
    ("lambda", "Function"): "AWS::Lambda::Function", ("lambda", "DockerImageFunction"): "AWS::Lambda::Function",
    ("s3", "Bucket"): "AWS::S3::Bucket", ("dynamodb", "Table"): "AWS::DynamoDB::Table",
    ("sqs", "Queue"): "AWS::SQS::Queue", ("sns", "Topic"): "AWS::SNS::Topic",
    ("apigateway", "RestApi"): "AWS::ApiGateway::RestApi", ("apigateway", "LambdaRestApi"): "AWS::ApiGateway::RestApi",
    ("rds", "DatabaseInstance"): "AWS::RDS::DBInstance", ("rds", "DatabaseCluster"): "AWS::RDS::DBInstance",
    ("elasticache", "CfnCacheCluster"): "AWS::ElastiCache::CacheCluster",
    ("cloudfront", "Distribution"): "AWS::CloudFront::Distribution",
}


def scan_cdk(root: Path, files: list[FileEntry], cdk_dirs: list[str], info: RepoInfo) -> None:
    n = 0
    for f in files:
        if not f.rel.endswith((".ts", ".py")) or f.size > 100_000 or is_test_path(f.rel):
            continue
        if not any(f.rel.startswith(d + "/") or not d for d in cdk_dirs):
            continue
        text = read_text(root / f.rel, 100_000)
        rx = CDK_NEW if f.rel.endswith(".ts") else CDK_PY
        for ns, cls, ident in rx.findall(text):
            t = CDK_MAP.get((ns.lower().replace("_", ""), cls)) or CDK_MAP.get((ns.split("_")[0], cls))
            if t:
                info.resources.append(resource("cdk", "aws", t, ident, f.rel))
                n += 1
        if n > 60:
            break
