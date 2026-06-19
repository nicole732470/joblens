# JobLens AWS resources (us-east-2)

Created during initial deploy. **Do not commit secrets.**

| Resource | ID / name |
|----------|-----------|
| VPC (default) | `vpc-0d1904c59a051b228` |
| EC2 security group | `sg-0930a7bda9f30016e` (`joblens-ec2`) — 22, 443, 8000 |
| RDS security group | `sg-0fea22f4c3f07b889` (`joblens-rds`) — 5432 from EC2 SG |
| RDS instance | `joblens-db` — **available** |
| RDS endpoint | `joblens-db.chu86icsovrl.us-east-2.rds.amazonaws.com` |
| RDS secret | `joblens/rds` in Secrets Manager |
| App secret | `joblens/app` |
| EC2 instance | `i-0bdee6f611283586f` (`joblens-api`, t3.small) |
| Elastic IP | `3.128.164.130` |
| IAM role | `joblens-ec2` |
| API (HTTP debug) | `http://3.128.164.130:8000/health` |

## Before launching EC2

```bash
aws secretsmanager create-secret --name joblens/app --secret-string '{
  "LLM_API_KEY": "sk-or-v1-...",
  "LLM_BASE_URL": "https://openrouter.ai/api/v1",
  "LLM_MODEL": "openai/gpt-oss-20b:free",
  "USE_REACT_AGENT": "false",
  "LANGSMITH_PROJECT": "joblens-analyze"
}'
```

## Launch EC2 (after RDS is `available`)

```bash
# IAM role joblens-ec2 must exist (SSM + secrets read)
aws ec2 run-instances \
  --image-id ami-0741dc526e1106ae5 \
  --instance-type t3.small \
  --security-group-ids sg-0930a7bda9f30016e \
  --iam-instance-profile Name=joblens-ec2 \
  --user-data file://deploy/ec2-user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=joblens-api}]'
```

## DATABASE_URL (once RDS is up)

```
postgresql://joblens:<password>@<rds-endpoint>:5432/joblens
```

Password: `aws secretsmanager get-secret-value --secret-id joblens/rds --query SecretString --output text`
