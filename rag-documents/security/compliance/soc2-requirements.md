# SOC2 Requirements

## Overview

Service Organization Control (SOC2) is a compliance framework established by the American Institute of Certified Public Accountants (AICPA) that provides guidelines for managing customer data and information security. SOC2 compliance is increasingly required for SaaS providers, cloud service providers, and any organization processing, storing, or transmitting customer data. This documentation outlines the core SOC2 requirements, implementation strategies, and operational procedures necessary to achieve and maintain compliance.

## Trust Service Criteria and Categories

### The Five Trust Service Principles

SOC2 compliance is built on five fundamental Trust Service Principles (TSCs) that organizations must address:

| Principle | Focus Area | Key Objectives |
|-----------|-----------|-----------------|
| Security (CC) | Overall security program | Protect systems and data from unauthorized access |
| Availability (A) | System uptime and performance | Ensure systems are available for authorized use |
| Processing Integrity (PI) | Complete and accurate processing | Maintain data accuracy throughout processing lifecycle |
| Confidentiality (C) | Data protection and privacy | Restrict access to sensitive information |
| Privacy (P) | Personal information handling | Manage personal data according to commitments |

### Common Criteria (CC) Control Categories

Most organizations focus on the Security principle, which encompasses 17 Common Criteria categories:

- **CC1-CC3**: Organization and governance controls
- **CC4-CC7**: Communication and information management
- **CC8-CC9**: System monitoring and risk assessment
- **CC10-CC17**: Logical and physical security controls

## Access Control and Authentication Requirements

### Identity and Access Management (IAM) Implementation

SOC2 requires documented procedures for managing user access with appropriate authentication and authorization controls.

**Required access control elements:**

- Multi-factor authentication (MFA) for all administrative access
- Role-based access control (RBAC) with principle of least privilege
- Documented access request and approval workflows
- Quarterly access reviews and recertification
- Automated deprovisioning of terminated employees within 24 hours
- Segregation of duties preventing conflicting system access

### MFA Configuration Example

```bash
# Enable MFA for SSH access
echo "ChallengeResponseAuthentication yes" >> /etc/ssh/sshd_config
echo "AuthenticationMethods publickey,password publickey,keyboard-interactive" >> /etc/ssh/sshd_config
systemctl restart sshd

# Configure time-based one-time password (TOTP)
# Users generate QR codes using:
# qrencode -o ~/totp_secret.png -d 200 -s 8 "otpauth://totp/user@example.com?secret=XXXXX"
```

### Access Review Procedures

Conduct quarterly access reviews with these steps:

1. Generate access reports from identity management systems
2. Assign reviews to business process owners
3. Verify current access aligns with job responsibilities
4. Document approval or removal decisions within review template
5. Remediate unauthorized access within 5 business days
6. Maintain signed evidence of completion

## Security Event Logging and Monitoring

### Audit Logging Requirements

All systems must implement comprehensive logging to support security monitoring and incident investigation:

- Log all authentication attempts (success and failure)
- Record administrative actions and configuration changes
- Track data access and modification events
- Preserve logs for minimum 90 days with searchable retention for 1 year
- Implement log forwarding to centralized SIEM (Security Information and Event Management)

### Log Aggregation Configuration

```yaml
# Example rsyslog configuration for centralized logging
# /etc/rsyslog.d/02-forward.conf
$ModLoad imtcp
$InputTCPServerRun 514

# Forward all logs to SIEM
*.* @@(z)siem-server.example.com:601;RSYSLOG_FileFormat

# Local backup retention
$ActionFileDefaultTemplate RSYSLOG_FileFormat
$FileOwner syslog
$FileGroup adm
$FileCreateMode 0640
$DirCreateMode 0755
$Umask 0022

# Separate critical logs
:syslogtag, contains, "auth" /var/log/auth.log
:syslogtag, contains, "admin" /var/log/admin.log
```

### Alert Configuration

Establish automated alerts for security events:

- More than 5 failed login attempts within 15 minutes
- Privilege escalation attempts
- Administrative account access outside business hours
- Configuration changes to security controls
- Unauthorized database access attempts
- Encryption key access or modification

## Incident Response and Management

### Incident Response Plan Components

A documented incident response plan must include:

- Clear roles and responsibilities for incident team members
- Step-by-step procedures for containment, eradication, and recovery
- Communication templates for internal and external notification
- Escalation procedures based on incident severity
- Post-incident review and documentation requirements

### Incident Classification and Timeline

```
Severity Level 1 (Critical):
- Response: Within 15 minutes
- Example: Active data breach, system outage
- Escalation: Notify executive team and legal

Severity Level 2 (High):
- Response: Within 1 hour
- Example: Unauthorized access attempt, malware detection
- Escalation: Security director and department heads

Severity Level 3 (Medium):
- Response: Within 4 hours
- Example: Policy violation, configuration drift
- Escalation: Information security team

Severity Level 4 (Low):
- Response: Within 24 hours
- Example: Failed backup, incomplete logging
- Escalation: Operations team
```

### Incident Documentation Template

Maintain incident records including:

1. **Initial Report**: Date, time, reporter, affected systems
2. **Investigation**: Timeline of events, root cause analysis
3. **Response Actions**: Containment steps, remediation measures
4. **Impact Assessment**: Data affected, systems compromised, business impact
5. **Corrective Actions**: Preventive measures to avoid recurrence
6. **Lessons Learned**: Review notes and process improvements

## System and Infrastructure Security

### Configuration Management Requirements

- Maintain baseline configurations for all systems
- Document and approve all configuration changes through change control process
- Implement automated configuration monitoring to detect unauthorized changes
- Remediate configuration drift within 24 hours of detection

### Vulnerability Management Procedures

**Required activities:**

- Quarterly vulnerability scanning of all systems and applications
- Monthly application dependency scanning for known CVEs
- Remediation timelines: Critical vulnerabilities within 15 days, High within 30 days
- Patch testing in non-production environments before deployment
- Documentation of risk acceptance for unpatched vulnerabilities

### Firewall and Network Segmentation

```
# Example firewall rules for network segmentation
# /etc/iptables/rules.v4

# Database tier - restricted access
-A INPUT -p tcp --dport 3306 -s 10.1.0.0/16 -j ACCEPT
-A INPUT -p tcp --dport 3306 -j DROP

# Web tier - limited inbound ports
-A INPUT -p tcp --dport 80 -j ACCEPT
-A INPUT -p tcp --dport 443 -j ACCEPT
-A INPUT -p tcp --dport 22 -s 10.0.1.0/24 -j ACCEPT

# Admin tier - strict access control
-A INPUT -p tcp --dport 9200 -s 10.2.0.0/16 -j ACCEPT
```

## Data Protection and Encryption

### Encryption Standards

- Encrypt all data in transit using TLS 1.2 or higher
- Encrypt sensitive data at rest using AES-256 or equivalent
- Implement key rotation every 90 days
- Maintain separate encryption keys for different data classifications
- Store encryption keys in dedicated key management system (KMS)

### Common Pitfalls and Troubleshooting

**Issue**: Encryption keys stored in configuration files or code repositories
- **Resolution**: Migrate keys to environment variables or dedicated KMS solutions
- **Prevention**: Implement pre-commit hooks to detect key patterns

**Issue**: Expired TLS certificates causing service interruptions
- **Resolution**: Automate certificate renewal at least 30 days before expiration
- **Prevention**: Monitor certificate expiration dates monthly

**Issue**: Inconsistent encryption across development and production environments
- **Resolution**: Document encryption requirements in architecture standards
- **Prevention**: Use infrastructure-as-code templates enforcing encryption

## Attestation and Audit Preparation

### Documentation Requirements

Maintain documentation of:

- Risk assessment results and remediation status
- Approved security policies and procedures
- Evidence of employee training completion
- Audit logs and monitoring reports
- Change control records for all modifications
- Business continuity and disaster recovery test results

### Auditor Expectations

External SOC2 auditors typically request:

- Network diagrams showing system architecture and data flows
- Evidence of design effectiveness (controls testing)
- Evidence of operational effectiveness (6+ months of logs)
- Screenshots of system controls in operation
- Interview access with personnel responsible for key controls

### Preparing for Type II Audit

A Type II SOC2 report requires operational testing over a minimum six-month period:

- Maintain continuous logs and monitoring data
- Execute annual disaster recovery test
- Complete quarterly access reviews with documentation
- Test backup and recovery procedures at least semi-annually
- Document all security incidents and responses

## Conclusion

SOC2 compliance requires a comprehensive, documented approach to security controls spanning access management, system monitoring, incident response, and data protection. Organizations should view SOC2 not merely as a compliance checkbox but as a framework for establishing mature security practices that protect customer data and organizational assets. Regular review, testing, and improvement of controls ensures continued compliance and strengthens overall security posture.