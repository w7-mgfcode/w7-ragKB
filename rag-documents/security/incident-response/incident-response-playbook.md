# Incident Response Playbook

## 1. Overview and Objectives

An incident response playbook provides a structured framework for detecting, containing, and remediating security incidents within an enterprise environment. This document establishes standardized procedures to minimize dwell time, reduce impact scope, and preserve evidence for forensic analysis.

### Purpose and Scope

This playbook applies to all security incidents affecting corporate information systems, including:

- Unauthorized access attempts
- Malware infections and command-and-control communications
- Data exfiltration and breach events
- Denial-of-service attacks
- Privilege escalation incidents
- Policy violations and suspicious user activity

### Key Performance Indicators

Effective incident response is measured through:

| Metric | Target | Definition |
|--------|--------|-----------|
| Mean Time to Detect (MTTD) | < 1 hour | Time from incident occurrence to detection |
| Mean Time to Respond (MTTR) | < 4 hours | Time from detection to initial containment |
| Evidence Preservation Rate | 100% | Percentage of incidents with chain-of-custody maintained |
| Stakeholder Notification | < 24 hours | Time to notify affected parties post-confirmation |

## 2. Detection and Alert Triage

### Alert Source Integration

Security incidents are identified through multiple detection mechanisms:

- SIEM (Security Information and Event Management) correlation rules
- Endpoint detection and response (EDR) agent alerts
- Network intrusion detection system (IDS) signatures
- User and entity behavior analytics (UEBA) anomalies
- Third-party threat intelligence feeds
- Internal system log analysis

### Initial Triage Process

Upon receiving an alert, the on-call incident responder must perform immediate triage:

1. **Verify Alert Authenticity**
   - Confirm the alert originated from a legitimate monitoring system
   - Cross-reference multiple data sources
   - Eliminate false positives from known system behaviors

2. **Assess Severity Level**
   - Determine initial risk classification (Critical, High, Medium, Low)
   - Document time of alert receipt
   - Create incident ticket in tracking system

3. **Preserve Initial Evidence**
   - Capture alert context and system screenshots
   - Document all affected systems and users
   - Note any ongoing malicious activity

### Alert Classification Example

```
ALERT: C2 Beacon Detection
Source: Network IDS
Rule: ET MALWARE Suspicious DNS Query to Known Botnet Domain
Severity: CRITICAL
Details:
  - Source IP: 192.168.50.145
  - Destination Domain: staging.dynamicns[.]net
  - Protocol: DNS (Port 53)
  - First Occurrence: 2024-01-15 14:32:18 UTC
  - Occurrences in past 24h: 47
Status: ESCALATE TO INCIDENT TEAM
```

## 3. Containment and Isolation

### Immediate Containment Actions

Containment objectives prevent incident escalation and limit damage scope. Actions depend on incident type and severity.

### Network Containment

For suspected network-based threats:

```bash
# Isolate affected host from network
# 1. Identify switch port
show cdp neighbors interface GigabitEthernet0/1/5

# 2. Disable port (does not delete VLAN membership)
configure terminal
interface GigabitEthernet0/1/5
shutdown
exit

# 3. Move host to isolated VLAN (optional for analysis)
vlan 999
name Incident_Isolation
exit

interface GigabitEthernet0/1/5
no shutdown
switchport access vlan 999
exit

# 4. Document the change
write memory
show interface GigabitEthernet0/1/5 status
```

### Endpoint Containment

For compromised endpoints:

1. **Immediate Isolation**
   - Disconnect from network (physical or logical)
   - Disable wireless connectivity
   - Prevent lateral movement to other systems

2. **Credential Reset**
   - Reset compromised user account passwords
   - Force re-authentication across all sessions
   - Monitor for continued unauthorized access

3. **Process Management**
   - Terminate suspicious processes while documenting PID and command line
   - Disable scheduled tasks and startup programs
   - Block command-and-control domains at firewall

### Isolation Network Configuration

Create a controlled environment for analysis:

```yaml
# Security Group Rules for Incident Isolation Network
Name: Incident-Isolation-SG
Rules:
  Inbound:
    - Protocol: TCP
      Port: 22 (SSH)
      Source: 10.0.0.0/24 (Incident Response Team)
      Description: Remote investigation access
    - Protocol: TCP
      Port: 3389 (RDP)
      Source: 10.0.0.0/24
      Description: Windows analysis access
  Outbound:
    - Protocol: TCP
      Port: 443
      Destination: 10.0.1.0/24 (Forensics Server)
      Description: Evidence transfer only
    - All Other: DENY
      Description: Prevent C2 communication during analysis
```

## 4. Investigation and Evidence Collection

### Forensic Evidence Preservation

Proper evidence handling is critical for both technical remediation and potential legal proceedings.

### Evidence Collection Hierarchy

Collect evidence in order of volatility, from most to least perishable:

1. **Live System State** (collect immediately)
   - Running processes and network connections
   - Memory contents (volatile RAM)
   - Current user sessions and login history
   - Open files and file handles
   - System memory dumps

2. **Filesystem Evidence** (collect within minutes)
   - Disk images with hash verification
   - Deleted files and unallocated clusters
   - File access timestamps (MAC times)
   - Log files with original timestamps preserved

3. **System Logs** (collect before restart)
   - Windows Event Viewer logs
   - Application-specific logs
   - Web server access logs
   - Authentication logs

### Linux Live Response Capture

```bash
#!/bin/bash
# Comprehensive evidence collection script
# Execute with elevated privileges
# Usage: ./collect_evidence.sh <incident_id> <output_directory>

INCIDENT_ID=$1
OUTPUT_DIR=$2
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EVIDENCE_DIR="${OUTPUT_DIR}/evidence_${INCIDENT_ID}_${TIMESTAMP}"

mkdir -p "${EVIDENCE_DIR}"

# Capture live system state
echo "Collecting live system evidence..."
ps auxww > "${EVIDENCE_DIR}/01_processes.txt"
netstat -anp > "${EVIDENCE_DIR}/02_network_connections.txt"
ss -antp > "${EVIDENCE_DIR}/03_sockets.txt"
w > "${EVIDENCE_DIR}/04_logged_in_users.txt"
lastlog > "${EVIDENCE_DIR}/05_login_history.txt"

# Capture filesystem metadata
find / -type f -newermt "2024-01-15 14:00:00" > "${EVIDENCE_DIR}/06_recent_files.txt" 2>/dev/null
lsof > "${EVIDENCE_DIR}/07_open_files.txt"

# Memory capture with dd
echo "Capturing system memory (this may take several minutes)..."
dd if=/dev/mem of="${EVIDENCE_DIR}/08_memory.dump" bs=1M conv=noerror,sync 2>&1

# Create hash manifest
cd "${EVIDENCE_DIR}"
sha256sum * > manifest.sha256
echo "Evidence collection complete. Location: ${EVIDENCE_DIR}"
```

### Chain of Custody Documentation

```
INCIDENT EVIDENCE LOG
Incident ID: INC-2024-001542
Description: Suspected credential theft and lateral movement

Evidence Item | Collected By | Date/Time | Hash (SHA256) | Storage Location | Accessed By
---|---|---|---|---|---
workstation-456.img | J. Smith | 2024-01-15 15:45 | a3f2e8d9c... | Evidence Server Slot 7 | J. Smith, M. Garcia
user-emails.zip | M. Garcia | 2024-01-15 16:20 | 7b4c2f9a1... | Evidence Server Slot 7 | M. Garcia
memory.dump | J. Smith | 2024-01-15 15:52 | 5e1d3g8h2... | Evidence Server Slot 8 | J. Smith, K. Patel
```

## 5. Eradication and Recovery

### Threat Eradication

After evidence collection and analysis, remove malicious artifacts:

### Malware Removal Procedure

1. **Identify all affected systems**
   - Correlate IOCs (Indicators of Compromise) across infrastructure
   - Review logs for lateral movement patterns
   - Identify secondary infections

2. **Deploy remediation**
   - Apply security patches and updates
   - Rebuild compromised systems from clean backups
   - Reimage endpoints if necessary
   - Remove persistence mechanisms (registry entries, scheduled tasks)

3. **Restore clean state**
   - Validate system integrity using file hashing
   - Restore from verified clean backups
   - Verify data integrity and completeness

### Recovery Validation Checklist

- [ ] All malicious processes terminated
- [ ] C2 domains blocked at firewall and DNS
- [ ] Suspicious cron jobs and scheduled tasks removed
- [ ] SSH public keys sanitized
- [ ] File permissions restored to expected values
- [ ] Security patches applied and verified
- [ ] EDR/antivirus signatures updated
- [ ] System monitoring enabled on recovered assets
- [ ] Change management documentation completed

## 6. Post-Incident Activities

### Incident Documentation and Reporting

Document all incident details in the tracking system before closure:

- **Executive Summary**: 2-3 paragraph overview for leadership
- **Timeline**: Chronological sequence of events with timestamps
- **Root Cause Analysis**: How the attacker gained initial access
- **Impact Assessment**: Data affected, systems compromised, remediation costs
- **Lessons Learned**: Process improvements and prevention recommendations

### Stakeholder Notification Requirements

| Stakeholder | Notification Timing | Required Information |
|---|---|---|
| Executive Leadership | Within 4 hours of containment | Severity, impact scope, remediation status |
| Legal/Compliance | Immediately for breaches | Affected data categories, notification obligations |
| Affected Users | Within 24 hours | What data was affected, recommended actions |
| Regulatory Bodies | Per regulatory requirements | Breach notification, investigation status |
| Insurance Provider | Within 48 hours | Incident summary, estimated costs |

### Prevention Recommendations

Following incident closure, implement improvements:

- Update detection signatures based on observed IOCs
- Enhance logging and monitoring in identified gaps
- Conduct security awareness training for affected departments
- Review and update access controls
- Implement additional segmentation if lateral movement occurred

---

**Document Version:** 1.2  
**Last Updated:** January 2024  
**Next Review Date:** July 2024