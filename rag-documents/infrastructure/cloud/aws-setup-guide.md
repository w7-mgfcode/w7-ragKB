# AWS Setup Guide

## Prerequisites and Account Configuration

Before deploying infrastructure on AWS, ensure your environment meets the baseline requirements and your AWS account is properly configured for enterprise operations.

### AWS Account Requirements

Your AWS account must have the following minimum setup completed:

- **Valid billing method** - A credit card or linked AWS Organizations payment method
- **IAM users created** - Avoid using root account for daily operations
- **MFA enabled** - Multi-factor authentication on all privileged accounts
- **CloudTrail enabled** - For audit logging and compliance tracking
- **AWS Organizations setup** - If managing multiple accounts or departments

### Initial Access Configuration

1. Navigate to the AWS Management Console
2. Create an administrative IAM user with programmatic access
3. Generate access keys (store securely in a password manager)
4. Configure the AWS CLI locally with your credentials:

```bash
aws configure
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: us-east-1
Default output format [None]: json
```

### Service Quotas and Limits

Review and request increases for the following common limits before production deployment:

| Service | Default Limit | Recommended Minimum |
|---------|---------------|-------------------|
| EC2 On-Demand Instances | 20 | 50 |
| RDS Instances | 40 | 50 |
| VPC Elastic IPs | 5 | 10 |
| NAT Gateways per AZ | Unlimited | Requires planning |

## VPC and Network Architecture

Establishing a robust network foundation is critical for security, performance, and compliance. This section covers the recommended Virtual Private Cloud configuration for enterprise deployments.

### VPC Creation and CIDR Planning

Create a VPC with proper CIDR block allocation to accommodate growth and avoid conflicts with on-premises networks:

1. Open the VPC dashboard in AWS Management Console
2. Click **Create VPC** and select **VPC only** option
3. Enter VPC name: `prod-vpc-us-east-1`
4. Set IPv4 CIDR block: `10.0.0.0/16`
5. Leave IPv6 disabled unless required
6. Enable DNS hostnames and DNS resolution in VPC settings

```json
{
  "VpcId": "vpc-0a1b2c3d4e5f6g7h8",
  "CidrBlock": "10.0.0.0/16",
  "InstanceTenancy": "default",
  "IsDefault": false,
  "Tags": [
    {
      "Key": "Name",
      "Value": "prod-vpc-us-east-1"
    },
    {
      "Key": "Environment",
      "Value": "Production"
    }
  ]
}
```

### Subnet Configuration Across Availability Zones

Deploy subnets across multiple availability zones for high availability. A typical three-tier architecture requires public and private subnets in at least two AZs:

- **Public Subnet AZ1**: `10.0.1.0/24` - Web tier
- **Private Subnet AZ1**: `10.0.2.0/24` - Application tier
- **Database Subnet AZ1**: `10.0.3.0/24` - Database tier
- **Public Subnet AZ2**: `10.0.11.0/24` - Web tier failover
- **Private Subnet AZ2**: `10.0.12.0/24` - Application tier failover
- **Database Subnet AZ2**: `10.0.13.0/24` - Database tier failover

### Route Tables and NAT Configuration

Create separate route tables for traffic control:

**Public Route Table Configuration:**
```
Destination: 0.0.0.0/0
Target: Internet Gateway (igw-xxxxxxxx)
```

**Private Route Table Configuration (NAT Gateway Method):**
1. Create Elastic IP for NAT Gateway: `aws ec2 allocate-address --domain vpc`
2. Create NAT Gateway in public subnet with allocated Elastic IP
3. Configure private route table:

```
Destination: 0.0.0.0/0
Target: NAT Gateway (nat-xxxxxxxx)
```

This allows private instances to initiate outbound connections while remaining inaccessible from the internet.

## Compute Instance Deployment

EC2 instances form the foundation of most AWS deployments. This section covers instance selection, security configuration, and deployment best practices.

### Instance Type Selection and Sizing

Choose instance types based on workload requirements. Common production selections include:

- **t3.medium** - Web servers, low-traffic applications, development environments
- **t3.large** - Standard application servers, moderate traffic
- **m5.xlarge** - General purpose, balanced compute/memory requirements
- **c5.xlarge** - Compute-optimized workloads, batch processing
- **r5.xlarge** - Memory-optimized, in-memory caching, large databases

Use AWS Compute Optimizer to analyze historical metrics and receive right-sizing recommendations.

### Launch Configuration with Security Groups

1. Launch an EC2 instance using Amazon Linux 2 AMI
2. Select appropriate instance type based on workload
3. Configure network settings:
   - VPC: Select your prod VPC
   - Subnet: Select public subnet for web tier
   - Auto-assign Public IP: Enable for web servers only
4. Create security group with inbound rules:

```
Type: HTTP
Protocol: TCP
Port: 80
Source: 0.0.0.0/0 (or specific CIDR range)

Type: HTTPS
Protocol: TCP
Port: 443
Source: 0.0.0.0/0

Type: SSH
Protocol: TCP
Port: 22
Source: YOUR_IP/32 (restrict to your IP)
```

### Instance Initialization and Configuration

Use EC2 User Data scripts for automatic configuration during instance launch:

```bash
#!/bin/bash
set -e
yum update -y
yum install -y httpd php php-mysql

# Enable and start services
systemctl enable httpd
systemctl start httpd

# Create health check page
echo "<?php echo 'Healthy'; ?>" > /var/www/html/health.php

# Configure CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm
```

## Storage and Database Configuration

Proper storage architecture ensures data durability, performance, and cost optimization.

### EBS Volume Configuration

For production applications, use EBS General Purpose (gp3) volumes with encryption:

```bash
aws ec2 create-volume \
  --availability-zone us-east-1a \
  --size 100 \
  --volume-type gp3 \
  --iops 3000 \
  --throughput 125 \
  --encrypted \
  --tag-specifications 'ResourceType=volume,Tags=[{Key=Name,Value=prod-app-volume-1}]'
```

**EBS Best Practices:**
- Enable encryption at rest for all volumes
- Configure automated snapshots every 24 hours
- Monitor volume performance metrics via CloudWatch
- Use io1/io2 volumes only for databases with intensive I/O requirements

### RDS Database Setup

1. Create DB subnet group spanning multiple availability zones
2. Launch RDS instance with Multi-AZ deployment enabled:
   - Engine: MySQL 8.0 or PostgreSQL 14+
   - Instance class: db.t3.small (minimum for production)
   - Storage: 100GB gp2 (encrypted)
   - Multi-AZ: Yes
   - Backup retention: 30 days
   - Backup window: 03:00-04:00 UTC

3. Configure security group allowing port 3306/5432 only from application tier subnet
4. Enable Enhanced Monitoring with 60-second granularity
5. Enable Performance Insights for query analysis

## Monitoring and Security Implementation

### CloudWatch Metrics and Alarms

Create essential CloudWatch alarms for operational visibility:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name prod-ec2-cpu-high \
  --alarm-description "Alert when EC2 CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:prod-alerts
```

### IAM Roles and Least Privilege Access

Create an IAM role for EC2 instances with minimal required permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:123456789012:log-group:/prod/app/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::prod-app-config/*"
    }
  ]
}
```

## Common Pitfalls and Troubleshooting

**Issue: Instances cannot reach RDS database**
- Verify database security group allows inbound traffic on database port from application security group
- Confirm DB subnet group contains subnets where application instances are deployed
- Check network ACLs for any deny rules

**Issue: High data transfer costs**
- Minimize cross-AZ data transfer by keeping related resources in same AZ when possible
- Use VPC endpoints for AWS service access to eliminate Internet Gateway charges
- Implement CloudFront for frequently accessed content

**Issue: SSH access denied to instances**
- Verify security group allows inbound SSH (port 22) from your IP address
- Confirm key pair permissions are 400: `chmod 400 key.pem`
- Check instance has network connectivity (public IP and route to Internet Gateway)