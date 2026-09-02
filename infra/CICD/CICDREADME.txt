Deploy Lambda Container via GitHub Actions (OIDC)
--------------------------------------------------

This workflow deploys a Docker container to AWS Lambda using OpenID Connect (OIDC).
With OIDC, GitHub Actions can securely access AWS without storing long-lived AWS credentials.

--------------------------------------------------

How It Works
------------

• GitHub Push  
• OIDC Token Generated  
• AWS STS AssumeRoleWithWebIdentity  
• Temporary Credentials Generated  
• Docker Image Pushed to Amazon ECR  
• Lambda Function Updated with New Image

--------------------------------------------------

Prerequisites
-------------

• AWS account with permissions to create IAM roles, OIDC providers, ECR repositories, and Lambda functions

• GitHub repository where the workflow will run

• AWS CLI installed locally

--------------------------------------------------

Step 1: Add GitHub as OIDC Provider in AWS
------------------------------------------

This is a one-time setup per AWS account.

AWS Console Steps:

• Go to IAM → Identity Providers  
• Click Add Provider  
• Select OpenID Connect  

Provide the following details:

• Provider URL = https://token.actions.githubusercontent.com  
• Click Get Thumbprint  
• Audience = sts.amazonaws.com  

Then click Add Provider.

--------------------------------------------------

Step 2: Create IAM Role for GitHub Actions
------------------------------------------

2.1 Create Trust Policy

Create a file named:

trust-policy.json

Replace placeholders before using.

{
 "Version": "2012-10-17",
 "Statement": [
   {
     "Effect": "Allow",
     "Principal": {
       "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
     },
     "Action": "sts:AssumeRoleWithWebIdentity",
     "Condition": {
       "StringEquals": {
         "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
       },
       "StringLike": {
         "token.actions.githubusercontent.com:sub": "repo:<YOUR_GITHUB_ORG>/<YOUR_REPO>:ref:refs/heads/main"
       }
     }
   }
 ]
}

--------------------------------------------------

--------------------------------------------------

Step 3: Create ECR Repository
-----------------------------

Create a repository to store the Docker image.

--------------------------------------------------

Step 4: Configure the GitHub Workflow
-------------------------------------

Update the following variables inside:

.github/workflows/deploy-lambda.yml

Required Variables:

• AWS_REGION = AWS region (example: us-east-1)

• ECR_REPOSITORY = Your ECR repository name

• LAMBDA_FUNCTION_NAME = Your Lambda function name

Example:

env:
 AWS_REGION: <YOUR_AWS_REGION>
 ECR_REPOSITORY: <YOUR_ECR_REPO_NAME>
 LAMBDA_FUNCTION_NAME: <YOUR_LAMBDA_FUNCTION_NAME>

Configure AWS credentials step:

role-to-assume: arn:aws:iam::<YOUR_ACCOUNT_ID>:role/<YOUR_ROLE_NAME>

--------------------------------------------------

Step 5: Enable OIDC Token Permission in GitHub
----------------------------------------------

The workflow requires the following permissions.

permissions:
 id-token: write
 contents: read

If restricted in your organization:

• Go to GitHub Repository Settings  
• Navigate to Actions → General  
• Under Workflow Permissions enable id-token: write

--------------------------------------------------

Troubleshooting
---------------

• Not authorized to perform sts:AssumeRoleWithWebIdentity  
  Check the OIDC provider URL and ensure the sub condition matches your repo and branch.

• no basic auth credentials (ECR)  
  Ensure the ECR login step runs before Docker build and push.

• id-token permission denied  
  Add id-token: write under workflow permissions.

• Lambda update fails  
  Verify the image URI is correct and the platform is linux/amd64.

• Workflow runs on wrong branch  
  Update ref:refs/heads/main in the trust policy.

--------------------------------------------------

Security Notes
--------------

• Do not use wildcard (*) in the trust policy sub condition.

• Always restrict access to a specific GitHub repository and branch.

• Use least-privilege IAM policies limited to required resources.

• Use separate IAM roles for different environments (dev, staging, prod).

• Do not store AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY in GitHub secrets when using OIDC.