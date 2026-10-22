"""Application framework detection from dependencies and config-file markers."""

from __future__ import annotations

from ..lists import add_unique
from ..model import RepoInfo
from .manifests import has


FRAMEWORKS: list[tuple[str, tuple[str, ...]]] = [
    ("FastAPI", ("fastapi",)),
    ("Django", ("django",)),
    ("Flask", ("flask",)),
    ("Celery", ("celery",)),
    ("Next.js", ("next",)),
    ("React", ("react", "react-dom")),
    ("Angular", ("@angular/core",)),
    ("Vue", ("vue",)),
    ("Nuxt", ("nuxt", "nuxt3")),
    ("Svelte", ("svelte", "@sveltejs/kit")),
    ("Remix", ("@remix-run/react", "@remix-run/node")),
    ("React Native", ("react-native",)),
    ("Electron", ("electron",)),
    ("NestJS", ("@nestjs/core",)),
    ("Express", ("express",)),
    ("Fastify", ("fastify",)),
    ("Spring Boot", ("spring-boot", "org.springframework.boot", "spring-boot-starter")),
    ("Quarkus", ("io.quarkus", "quarkus-resteasy")),
    ("ASP.NET Core", ("microsoft.aspnetcore", "sdk:microsoft.net.sdk.web")),
    (".NET Azure Functions", ("microsoft.azure.functions", "microsoft.net.sdk.functions", "microsoft.azure.webjobs")),
    ("Azure Functions", ("azure-functions", "@azure/functions")),
    ("AWS Lambda", ("aws-lambda-powertools", "@types/aws-lambda", "aws-lambda", "mangum", "serverless-http",
                    "amazon.lambda.core", "com.amazonaws:aws-lambda-java-core")),
    ("Gin", ("github.com/gin-gonic/gin",)),
    ("Echo", ("github.com/labstack/echo",)),
    ("Fiber", ("github.com/gofiber/fiber",)),
    ("Rails", ("rails",)),
    ("Laravel", ("laravel/framework",)),
    ("Symfony", ("symfony/framework-bundle",)),
    ("Actix", ("actix-web",)),
    ("Axum", ("axum",)),
]


FRONTEND = {"React", "Next.js", "Angular", "Vue", "Nuxt", "Svelte", "Remix", "React Native", "Electron"}

BACKEND = {"FastAPI", "Django", "Flask", "Express", "Fastify", "NestJS", "Spring Boot", "Quarkus", "ASP.NET Core",
            "Gin", "Echo", "Fiber", "Rails", "Laravel", "Symfony", "Actix", "Axum"}


def detect_frameworks(info: RepoInfo, deps: set[str], markers: set[str]) -> None:
    for fw, names in FRAMEWORKS:
        if has(deps, names):
            add_unique(info.frameworks, fw)
    if "next" in markers:
        add_unique(info.frameworks, "Next.js")
    if "angular" in markers:
        add_unique(info.frameworks, "Angular")
    if "nuxt" in markers:
        add_unique(info.frameworks, "Nuxt")
    if "svelte" in markers:
        add_unique(info.frameworks, "Svelte")
    if "django" in markers and "Django" not in info.frameworks:
        info.frameworks.append("Django")
    if "azure-functions" in markers and not any("Azure Functions" in f for f in info.frameworks):
        info.frameworks.append(".NET Azure Functions" if "C#" in info.languages else "Azure Functions")
    if "serverless" in markers or "sam" in markers or any(r["type"].startswith("AWS::Serverless") for r in info.resources):
        if any(r["provider"] == "aws" for r in info.resources if r["iac"] in ("serverless", "sam")):
            add_unique(info.frameworks, "AWS Lambda")
    # Next.js ships React; keep both but put the meta-framework first.
    if "Next.js" in info.frameworks and "React" in info.frameworks:
        info.frameworks.remove("React")
        info.frameworks.insert(info.frameworks.index("Next.js") + 1, "React")
