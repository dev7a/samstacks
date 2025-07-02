---
title: "Output Masking"
weight: 40
---

Protect sensitive information in deployment outputs, reports, and logs with comprehensive data masking.

## Overview

The output masking feature automatically identifies and masks sensitive data in all samstacks outputs, including console displays, deployment reports, pipeline summaries, and template expressions. This helps protect sensitive information when sharing deployment artifacts, logs, or reports.

## Quick Start

Enable comprehensive masking with minimal configuration:

```yaml {filename="pipeline.yml"}
pipeline_settings:
  output_masking:
    enabled: true  # Enables ALL categories by default

stacks:
  - id: my-stack
    dir: ./my-stack
```

Or enable specific categories only:

```yaml {filename="pipeline.yml"}
pipeline_settings:
  output_masking:
    enabled: true
    categories:
      account_ids: true      # Only enable account ID masking
      api_endpoints: true    # Only enable API endpoint masking

stacks:
  - id: my-stack
    dir: ./my-stack
```

**Result:**
```
# Before masking
FunctionArn: arn:aws:lambda:us-west-2:123456789012:function:my-function

# After masking  
FunctionArn: arn:aws:lambda:us-west-2:************:function:my-function
```

## Configuration

### Basic Configuration

**Simple (enables all categories by default):**
```yaml {filename="pipeline.yml"}
pipeline_settings:
  output_masking:
    enabled: true  # Enables ALL categories automatically
```

**Explicit (same effect, but shows all available options):**
```yaml {filename="pipeline.yml"}
pipeline_settings:
  output_masking:
    enabled: true  # Master switch for all masking
    categories:
      account_ids: true        # AWS account IDs (12-digit numbers)
      api_endpoints: true      # API Gateway and Lambda Function URLs
      database_endpoints: true # RDS, ElastiCache, DocumentDB endpoints
      load_balancer_dns: true  # ALB, NLB, CLB DNS names
      cloudfront_domains: true # CloudFront distribution domains
      s3_bucket_domains: true  # S3 website and transfer endpoints
      ip_addresses: true       # IPv4 and IPv6 addresses
```

### Advanced Configuration with Custom Patterns

```yaml {filename="pipeline.yml"}
pipeline_settings:
  output_masking:
    enabled: true
    categories:
      account_ids: true
      api_endpoints: true
    custom_patterns:
      - pattern: "secret-[a-zA-Z0-9]+"
        replacement: "secret-***"
        description: "Mask secret tokens"
      - pattern: "key-[0-9]+"
        replacement: "key-***"
        description: "Mask API keys"
```

## Masking Categories

### Account IDs

Masks 12-digit AWS account IDs in various contexts:

**Patterns detected:**
- ARNs: `arn:aws:service:region:123456789012:resource`
- SQS URLs: `https://sqs.region.amazonaws.com/123456789012/queue`
- S3 bucket names with account IDs: `mybucket-123456789012`

**Examples:**
```yaml
# Input
FunctionArn: arn:aws:lambda:us-west-2:123456789012:function:processor
QueueUrl: https://sqs.us-west-2.amazonaws.com/123456789012/notifications

# Output  
FunctionArn: arn:aws:lambda:us-west-2:************:function:processor
QueueUrl: https://sqs.us-west-2.amazonaws.com/************/notifications
```

### API Endpoints

Masks API Gateway and Lambda Function URLs:

**Patterns detected:**
- API Gateway: `https://{api-id}.execute-api.region.amazonaws.com`
- Lambda Function URLs: `https://{function-url}.lambda-url.region.on.aws`
- Custom domains: `https://{subdomain}.{domain}.com/api`

**Examples:**
```yaml
# Input
ApiUrl: https://abc123def.execute-api.us-west-2.amazonaws.com/prod
FunctionUrl: https://xyz789ghi.lambda-url.us-east-1.on.aws/

# Output
ApiUrl: https://******.execute-api.us-west-2.amazonaws.com/prod  
FunctionUrl: https://******.lambda-url.us-east-1.on.aws/
```

### Database Endpoints

Masks database connection endpoints:

**Patterns detected:**
- RDS: `{instance}.{random}.region.rds.amazonaws.com`
- ElastiCache: `{cluster}.{random}.cache.amazonaws.com`
- DocumentDB: `{cluster}.{random}.docdb.amazonaws.com`
- Neptune: `{cluster}.{random}.neptune.amazonaws.com`

**Examples:**
```yaml
# Input
DatabaseEndpoint: myapp.abc123.us-west-2.rds.amazonaws.com
CacheEndpoint: redis.def456.cache.amazonaws.com

# Output
DatabaseEndpoint: myapp.******.us-west-2.rds.amazonaws.com
CacheEndpoint: redis.******.cache.amazonaws.com
```

### Load Balancer DNS

Masks Elastic Load Balancer DNS names:

**Patterns detected:**
- Application Load Balancer: `{name}-{random}.region.elb.amazonaws.com`
- Network Load Balancer: `{name}-{random}.elb.region.amazonaws.com`
- Classic Load Balancer: `{name}-{random}.region.elb.amazonaws.com`

**Examples:**
```yaml
# Input
LoadBalancerDns: my-app-alb-1234567890.us-west-2.elb.amazonaws.com

# Output
LoadBalancerDns: my-app-alb-*********.us-west-2.elb.amazonaws.com
```

### CloudFront Domains

Masks CloudFront distribution domains:

**Examples:**
```yaml
# Input
CdnDomain: d1a2b3c4d5e6f.cloudfront.net

# Output
CdnDomain: d************.cloudfront.net
```

### S3 Bucket Domains

Masks S3 website and transfer acceleration endpoints:

**Patterns detected:**
- Website endpoints: `{bucket}.s3-website-region.amazonaws.com`
- Transfer acceleration: `{bucket}.s3-accelerate.amazonaws.com`
- Dual-stack: `{bucket}.s3.dualstack.region.amazonaws.com`

**Examples:**
```yaml
# Input
WebsiteUrl: mybucket.s3-website-us-west-2.amazonaws.com
AccelerateUrl: mybucket.s3-accelerate.amazonaws.com

# Output
WebsiteUrl: ********.s3-website-us-west-2.amazonaws.com
AccelerateUrl: ********.s3-accelerate.amazonaws.com
```

### IP Addresses

Masks IPv4 and IPv6 addresses:

**Examples:**
```yaml
# Input
ServerIp: 192.168.1.100
ServerIpv6: 2001:db8::1

# Output
ServerIp: ***.***.***.***
ServerIpv6: ****:***::*
```

## Custom Patterns

Define application-specific masking patterns using regular expressions:

```yaml {filename="pipeline.yml"}
pipeline_settings:
  output_masking:
    enabled: true
    custom_patterns:
      # Mask secret tokens
      - pattern: "secret-[a-zA-Z0-9]+"
        replacement: "secret-***"
        description: "Application secret tokens"
      
      # Mask API keys  
      - pattern: "ak-[0-9]+"
        replacement: "ak-***"
        description: "API access keys"
        
      # Mask database passwords in connection strings
      - pattern: "password=[^;\\s]+"
        replacement: "password=***"
        description: "Database passwords"
        
      # Mask JWT tokens
      - pattern: "eyJ[A-Za-z0-9-_=]+\\.[A-Za-z0-9-_=]+\\.?[A-Za-z0-9-_.+/=]*"
        replacement: "eyJ***"
        description: "JWT tokens"
```

**Custom pattern rules:**
- Use standard regex syntax
- Escape special characters appropriately
- Test patterns thoroughly before deployment
- Keep replacements consistent for the same data type

## Masking Scope

Output masking applies to:

### Console Output
- Stack parameter displays during deployment
- Stack output displays after deployment
- Pipeline summary rendering
- Error messages and logs

### Deployment Reports
- Console summary reports (`samstacks deploy`)
- Markdown file reports (`--report-file`)
- Stack parameter tables
- Stack output tables

### Pipeline Summaries
- Post-deployment summary content
- Template expression evaluation in summaries
- Markdown rendering of summary content

### Template Expressions
All template expressions are processed through masking when enabled:
- `${{ stacks.my-stack.outputs.SensitiveData }}`
- Pipeline summary content containing sensitive data
- Environment variable resolution

## Best Practices

### Security Guidelines

1. **Enable comprehensive masking** for production pipelines:
   ```yaml
   output_masking:
     enabled: true  # This alone enables all security categories
   ```

2. **Use custom patterns** for application-specific secrets:
   ```yaml
   custom_patterns:
     - pattern: "your-app-secret-[a-zA-Z0-9]+"
       replacement: "your-app-secret-***"
   ```

3. **Validate patterns** in development before production deployment

4. **Document masking rules** in your team's deployment procedures

### Development Workflow

1. **Development**: Start with masking disabled for easier debugging
2. **Staging**: Enable relevant masking categories to test patterns
3. **Production**: Enable comprehensive masking for security

```yaml
# Development
pipeline_settings:
  output_masking:
    enabled: false

# Staging  
pipeline_settings:
  output_masking:
    enabled: true
    categories:
      account_ids: true

# Production
pipeline_settings:
  output_masking:
    enabled: true
    categories:
      account_ids: true
      api_endpoints: true
      database_endpoints: true
      load_balancer_dns: true
      cloudfront_domains: true
      s3_bucket_domains: true
      ip_addresses: true
```

### CI/CD Integration

For CI/CD pipelines, enable masking to protect logs and artifacts:

```yaml
# GitHub Actions example
- name: Deploy with masked outputs
  run: |
    uvx samstacks deploy pipeline.yml --report-file deployment-report.md
    
- name: Upload masked report
  uses: actions/upload-artifact@v3
  with:
    name: deployment-report
    path: deployment-report.md
```

## Performance Considerations

- Masking adds minimal overhead to deployment
- Custom patterns are evaluated in order - place more specific patterns first
- Complex regex patterns may impact performance with large outputs
- Consider the number of custom patterns (recommended: < 10)

## Troubleshooting

### Common Issues

**Pattern not matching:**
```yaml
# Problem: Pattern too specific
pattern: "secret-123456"

# Solution: Use broader pattern  
pattern: "secret-[0-9]+"
```

**Unexpected masking:**
```yaml
# Problem: Pattern too broad
pattern: "[0-9]+"  # Masks all numbers

# Solution: Be more specific
pattern: "key-[0-9]+"  # Only masks key- prefixed numbers
```

**Masking not applied:**
```yaml
# Problem: Master switch disabled
output_masking:
  enabled: false  # Must be true
  categories:
    account_ids: true
```

### Testing Patterns

Use a test pipeline to validate custom patterns:

```yaml {filename="test-masking.yml"}
pipeline_name: Masking Test
pipeline_settings:
  output_masking:
    enabled: true
    custom_patterns:
      - pattern: "test-[a-z]+"
        replacement: "test-***"

stacks:
  - id: test-stack
    dir: ./test-stack
    params:
      TestValue: "test-secret-data"
```

## Examples

### Complete E-commerce Application

```yaml {filename="ecommerce-pipeline.yml"}
pipeline_name: E-commerce Platform
pipeline_description: Secure deployment with comprehensive masking

pipeline_settings:
  output_masking:
    enabled: true
    categories:
      account_ids: true
      api_endpoints: true
      database_endpoints: true
      load_balancer_dns: true
      ip_addresses: true
    custom_patterns:
      - pattern: "stripe_[a-zA-Z0-9_]+"
        replacement: "stripe_***"
        description: "Stripe API keys"
      - pattern: "jwt_[A-Za-z0-9-_=]+\\.[A-Za-z0-9-_=]+\\.?[A-Za-z0-9-_.+/=]*"
        replacement: "jwt_***"
        description: "JWT tokens"

stacks:
  - id: database
    dir: ./infrastructure/database
    
  - id: api
    dir: ./application/api
    params:
      DatabaseUrl: ${{ stacks.database.outputs.ConnectionString }}
      
  - id: frontend
    dir: ./application/frontend
    params:
      ApiEndpoint: ${{ stacks.api.outputs.ApiUrl }}

summary: |
  # 🛡️ Secure Deployment Complete
  
  Your e-commerce platform has been deployed with comprehensive security masking.
  
  ## Key Endpoints
  - **API**: ${{ stacks.api.outputs.ApiUrl }}
  - **Database**: ${{ stacks.database.outputs.ConnectionString }}
  - **Load Balancer**: ${{ stacks.api.outputs.LoadBalancerDns }}
  
  All sensitive data above has been automatically masked for security.
```

This configuration ensures that all deployment outputs, reports, and logs protect sensitive information while maintaining useful deployment visibility. 