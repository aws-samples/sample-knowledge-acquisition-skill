from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnOutput,
    aws_cognito as cognito,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_sns as sns,
    aws_events as events,
    aws_events_targets as targets,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
)
from constructs import Construct

from stacks.solution import SOLUTION_USER_AGENT


class WikiPlatformStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Shared layer providing the AWS Solutions user-agent hook to the
        # Python Lambdas below (defined once, in infrastructure/layers).
        solution_user_agent_layer = _lambda.LayerVersion(
            self,
            "SolutionUserAgentLayer",
            code=_lambda.Code.from_asset("layers/solution_user_agent"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="AWS Solutions usage-tracking user-agent hook (solution_user_agent)",
        )

        # 1. Cognito User Pool
        user_pool = cognito.UserPool(
            self,
            "WikiUserPool",
            self_sign_up_enabled=False,
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_uppercase=True,
                require_lowercase=True,
                require_symbols=True,
            ),
        )

        # 2. Cognito User Pool Client
        user_pool_client = user_pool.add_client(
            "WikiUserPoolClient",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=True,
            ),
        )

        # 3. SNS Topic
        wiki_changes_topic = sns.Topic(
            self,
            "WikiChangesTopic",
            topic_name="wiki-changes",
        )

        # 4. S3 Log Buckets (must be created before the UI bucket)
        cloudfront_log_bucket = s3.Bucket(
            self,
            "CloudFrontLogBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            object_ownership=s3.ObjectOwnership.OBJECT_WRITER,
        )

        ui_log_bucket = s3.Bucket(
            self,
            "UILogBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            object_ownership=s3.ObjectOwnership.OBJECT_WRITER,
        )

        # 5. S3 Bucket (React UI)
        ui_bucket = s3.Bucket(
            self,
            "ReactUIBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            server_access_logs_bucket=ui_log_bucket,
        )

        # 6. Lambda: wiki-reader (Node.js 20)
        wiki_reader_fn = _lambda.Function(
            self,
            "WikiReaderFunction",
            function_name="wiki-reader",
            runtime=_lambda.Runtime.NODEJS_20_X,
            handler="index.handler",
            code=_lambda.Code.from_asset("lambda/wiki_api"),
            memory_size=256,
            timeout=Duration.seconds(15),
            environment={
                "DEFAULT_BRANCH": "main",
                "USER_AGENT_STRING": SOLUTION_USER_AGENT,
            },
        )

        wiki_reader_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "codecommit:Get*",
                    "codecommit:BatchGetCommits",
                    "codecommit:ListBranches",
                ],
                resources=[
                    f"arn:aws:codecommit:{self.region}:{self.account}:wiki-*"
                ],
            )
        )

        wiki_reader_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParametersByPath"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/wikis/*"
                ],
            )
        )

        # 7. Lambda: wiki-admin (Python 3.12)
        wiki_admin_fn = _lambda.Function(
            self,
            "WikiAdminFunction",
            function_name="wiki-admin",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambda/wiki_admin"),
            memory_size=256,
            timeout=Duration.seconds(30),
            layers=[solution_user_agent_layer],
            environment={
                "DEFAULT_BRANCH": "main",
                "SNS_TOPIC_ARN": wiki_changes_topic.topic_arn,
                "USER_AGENT_STRING": SOLUTION_USER_AGENT,
            },
        )

        wiki_admin_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "codecommit:Create*",
                    "codecommit:Delete*",
                    "codecommit:Tag*",
                    "codecommit:GetRepository",
                ],
                resources=[
                    f"arn:aws:codecommit:{self.region}:{self.account}:wiki-*"
                ],
            )
        )

        wiki_admin_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:PutParameter", "ssm:DeleteParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/wikis/*"
                ],
            )
        )

        wiki_admin_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:DeleteObject"],
                resources=[f"{ui_bucket.bucket_arn}/data/*"],
            )
        )

        # 8. Lambda: wiki-indexer (Python 3.12)
        wiki_indexer_fn = _lambda.Function(
            self,
            "WikiIndexerFunction",
            function_name="wiki-indexer",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambda/wiki_indexer"),
            memory_size=1024,
            timeout=Duration.seconds(120),
            layers=[solution_user_agent_layer],
            environment={
                "DEFAULT_BRANCH": "main",
                "DATA_BUCKET": ui_bucket.bucket_name,
                "USER_AGENT_STRING": SOLUTION_USER_AGENT,
            },
        )

        wiki_indexer_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "codecommit:GetBranch",
                    "codecommit:GetFolder",
                    "codecommit:GetFile",
                ],
                resources=[
                    f"arn:aws:codecommit:{self.region}:{self.account}:wiki-*"
                ],
            )
        )

        wiki_indexer_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[f"{ui_bucket.bucket_arn}/data/*"],
            )
        )

        wiki_indexer_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudfront:CreateInvalidation"],
                resources=["*"],
            )
        )

        # 9. API Gateway HTTP API
        http_api = apigwv2.HttpApi(
            self,
            "WikiHttpApi",
            api_name="WikiPlatformAPI",
        )

        # Update wiki-indexer env with distribution ID placeholder (set after distribution creation)
        # We'll use a lazy reference via Fn after CloudFront is created

        # JWT Authorizer
        jwt_authorizer = apigwv2_authorizers.HttpJwtAuthorizer(
            "CognitoJwtAuthorizer",
            jwt_issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}",
            jwt_audience=[user_pool_client.user_pool_client_id],
        )

        # IAM Authorizer
        iam_authorizer = apigwv2_authorizers.HttpIamAuthorizer()

        # Lambda integrations
        reader_integration = apigwv2_integrations.HttpLambdaIntegration(
            "WikiReaderIntegration", wiki_reader_fn
        )

        admin_integration = apigwv2_integrations.HttpLambdaIntegration(
            "WikiAdminIntegration", wiki_admin_fn
        )

        # Routes
        # GET /api/{proxy+} → wiki-reader (no authorizer specified = open, but typically JWT)
        http_api.add_routes(
            path="/api/{proxy+}",
            methods=[apigwv2.HttpMethod.GET],
            integration=reader_integration,
        )

        # POST /api/wikis → wiki-admin (IAM authorizer — JWT+IAM means IAM layer)
        http_api.add_routes(
            path="/api/wikis",
            methods=[apigwv2.HttpMethod.POST],
            integration=admin_integration,
            authorizer=iam_authorizer,
        )

        # DELETE /api/wikis → wiki-admin (JWT only)
        http_api.add_routes(
            path="/api/wikis",
            methods=[apigwv2.HttpMethod.DELETE],
            integration=admin_integration,
            authorizer=jwt_authorizer,
        )

        # 10. CloudFront Distribution
        oac = cloudfront.S3OriginAccessControl(
            self,
            "WikiOAC",
        )

        s3_origin = origins.S3BucketOrigin.with_origin_access_control(
            ui_bucket,
            origin_access_control=oac,
        )

        api_origin = origins.HttpOrigin(
            f"{http_api.http_api_id}.execute-api.{self.region}.amazonaws.com",
        )

        distribution = cloudfront.Distribution(
            self,
            "WikiDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=s3_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                ),
            },
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            log_bucket=cloudfront_log_bucket,
        )

        # Set DISTRIBUTION_ID env on wiki-indexer now that distribution is created
        wiki_indexer_fn.add_environment("DISTRIBUTION_ID", distribution.distribution_id)

        # 11. EventBridge Rule
        codecommit_rule = events.Rule(
            self,
            "WikiCodeCommitRule",
            event_pattern=events.EventPattern(
                source=["aws.codecommit"],
                detail_type=["CodeCommit Repository State Change"],
                detail={"event": ["referenceUpdated"]},
            ),
        )

        codecommit_rule.add_target(targets.LambdaFunction(wiki_indexer_fn))

        # 12. IAM Role (WikiAgentRole)
        wiki_agent_role = iam.Role(
            self,
            "WikiAgentRole",
            role_name="WikiAgentRole",
            assumed_by=iam.AccountRootPrincipal(),
        )

        wiki_agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=["codecommit:GitPull", "codecommit:GitPush"],
                resources=[
                    f"arn:aws:codecommit:{self.region}:{self.account}:wiki-*"
                ],
            )
        )

        wiki_agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParametersByPath", "ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/wikis/*"
                ],
            )
        )

        wiki_agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sns:Subscribe", "sns:Receive"],
                resources=[wiki_changes_topic.topic_arn],
            )
        )

        # 13. CfnOutputs
        CfnOutput(
            self,
            "WebAppURL",
            value=f"https://{distribution.distribution_domain_name}",
        )

        CfnOutput(
            self,
            "CognitoUserPoolId",
            value=user_pool.user_pool_id,
        )

        CfnOutput(
            self,
            "CognitoClientId",
            value=user_pool_client.user_pool_client_id,
        )

        CfnOutput(
            self,
            "ApiEndpoint",
            value=http_api.api_endpoint,
        )

        CfnOutput(
            self,
            "ReactUIBucketName",
            value=ui_bucket.bucket_name,
        )

        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=distribution.distribution_id,
        )

        CfnOutput(
            self,
            "WikiAgentRoleArn",
            value=wiki_agent_role.role_arn,
        )

        CfnOutput(
            self,
            "WikiChangesTopicArn",
            value=wiki_changes_topic.topic_arn,
        )
