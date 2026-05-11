# VPN Configuration

## Overview

Virtual Private Networks (VPNs) provide secure, encrypted communication channels for remote users and distributed networks to access corporate resources. This document provides comprehensive guidance on configuring VPN infrastructure, including site-to-site and remote access implementations, security protocols, and operational best practices for enterprise environments.

## VPN Architecture and Types

### Site-to-Site VPN Configuration

Site-to-site VPNs establish persistent, encrypted tunnels between two or more physical network locations. This architecture enables seamless communication between corporate data centers, branch offices, and cloud infrastructure.

**Key Components:**
- VPN gateways at each site
- IPsec or SSL/TLS encryption protocols
- Dynamic or static routing protocols
- Redundant connections for failover capability

### Remote Access VPN Setup

Remote access VPNs allow individual users to securely connect to corporate networks from external locations. This configuration supports hybrid work environments and requires robust authentication mechanisms.

**Architecture Elements:**
- VPN concentrator or gateway appliance
- Client software or native OS VPN support
- Multi-factor authentication (MFA) integration
- Split tunneling policies (typically disabled for security)

### Hybrid Cloud VPN Implementation

Hybrid cloud VPN configurations connect on-premises infrastructure with cloud service providers through encrypted tunnels. This enables secure data transfer and unified network management across hybrid environments.

## Security Protocols and Encryption Standards

### IPsec Configuration

IPsec operates at Layer 3 and provides authentication and encryption for IP traffic. Configure IPsec with the following parameters:

```
Encryption Algorithm: AES-256-GCM
Authentication Algorithm: SHA-384
Diffie-Hellman Group: DH Group 20
IKE Version: IKEv2
Rekey Interval: 3600 seconds
```

**IKE Phase 1 Configuration:**
- Encryption: AES-256
- Hash: SHA-256 or stronger
- DH Group: 14 or higher
- Lifetime: 28800 seconds

**IKE Phase 2 Configuration:**
- Encryption: AES-256-GCM
- Authentication: SHA-384
- Lifetime: 3600 seconds

### SSL/TLS VPN Configuration

SSL/TLS VPNs provide application-layer encryption and browser-based access without client software installation. Configure with the following minimum standards:

```
TLS Version: 1.2 or 1.3
Cipher Suites: TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
Certificate: SHA-256 signed, 2048-bit RSA minimum
HSTS: Enabled with 31536000 second max-age
```

## Deployment and Configuration Procedures

### Pre-Deployment Requirements

Before implementing VPN infrastructure, ensure the following prerequisites are met:

- Network topology documentation and IP addressing scheme
- Firewall rules allowing VPN traffic (UDP 500, 4500, TCP 443)
- Certificate infrastructure for authentication (PKI or self-signed)
- Backup connectivity and failover mechanisms
- Bandwidth capacity assessment for peak usage

### Step-by-Step Implementation

**1. Gateway Configuration**

Configure VPN gateway parameters including local and remote network definitions:

```
[Gateway Configuration]
local_network: 10.0.0.0/8
remote_network: 192.168.0.0/16
gateway_ip: 203.0.113.10
tunnel_address: 172.16.0.1
```

**2. Encryption and Authentication Setup**

Deploy cryptographic parameters and certificate installation:

```bash
# Generate self-signed certificate (90-day validity)
openssl req -x509 -newkey rsa:2048 -keyout vpn.key \
  -out vpn.crt -days 90 -nodes \
  -subj "/C=US/ST=State/L=City/O=Company/CN=vpn.company.com"

# Install certificate on VPN gateway
vpn-gateway install-cert vpn.crt vpn.key
```

**3. Tunnel Configuration**

Establish encrypted tunnel parameters between endpoints:

```
[Tunnel_Configuration]
tunnel_name: site-to-site-primary
local_endpoint: 203.0.113.10
remote_endpoint: 198.51.100.20
protocol: ikev2
pfs_group: 20
rekey_margin: 540
```

**4. Routing Configuration**

Configure static or dynamic routing for traffic destined to remote networks:

```
# Static route for remote network via VPN gateway
ip route 192.168.0.0/16 172.16.0.2 description "Remote_Site_Route"

# Dynamic routing (BGP example)
router bgp 65001
  neighbor 172.16.0.2 remote-as 65002
  address-family ipv4
    network 10.0.0.0 mask 255.0.0.0
    neighbor 172.16.0.2 activate
```

### Remote Access VPN Client Configuration

**Windows Client Example:**

```
[VPN Connection Settings]
ConnectionName: Corporate_VPN
ServerAddress: vpn.company.com
EncryptionType: Required
Protocol: IKEv2
AuthenticationMethod: EAP-MSCHAPv2
RequireMFA: True
```

**Linux Client Configuration:**

```bash
# strongSwan configuration (/etc/ipsec.conf)
conn corporate-vpn
  left=192.168.1.100
  leftauth=eap
  right=vpn.company.com
  rightauth=pubkey
  rightsendcert=always
  type=tunnel
  auto=start
```

## Monitoring and Troubleshooting

### Performance Metrics and Monitoring

Monitor VPN tunnel health using these critical metrics:

| Metric | Threshold | Alert Level |
|--------|-----------|------------|
| Tunnel Status | Active | Critical if down |
| Packet Loss | <1% | Warning if >2% |
| Latency | <100ms | Warning if >150ms |
| Throughput | >90% capacity | Warning if exceeded |
| Connection Stability | >99.9% uptime | Alert if degraded |

### Common Issues and Resolution

**Issue: Tunnel Drops Intermittently**

Check for firewall rules blocking keepalive packets:

```bash
# Enable DPD (Dead Peer Detection)
dpd_action = restart
dpd_timeout = 60
dpd_delay = 30
```

**Issue: Slow Throughput Over VPN**

Diagnose MTU issues and optimize encryption settings:

```bash
# Test path MTU
ping -M do -s 1472 remote-gateway.com

# Reduce MTU on tunnel interface if necessary
ip link set dev vpn0 mtu 1436
```

**Issue: Authentication Failures**

Verify certificate validity and credential synchronization:

```bash
# Check certificate expiration
openssl x509 -in vpn.crt -noout -dates

# Verify RADIUS/LDAP connectivity
radiustest -h 10.0.0.50 -u testuser -p testpass
```

## Best Practices and Recommendations

### Security Hardening

- Implement certificate pinning to prevent man-in-the-middle attacks
- Disable legacy algorithms (DES, MD5, DH Group 1)
- Enforce strict firewall rules limiting VPN traffic to necessary ports
- Require multi-factor authentication for all remote access VPNs
- Rotate VPN credentials and certificates annually
- Maintain detailed audit logs with minimum 90-day retention

### Operational Excellence

- Deploy redundant VPN gateways in active-passive or active-active configurations
- Schedule certificate renewal at least 30 days before expiration
- Test failover scenarios quarterly to ensure recovery procedures
- Document all VPN configurations in change management system
- Implement automated health checks and alerting mechanisms
- Conduct annual security audits and penetration testing

### Capacity Planning

- Establish baseline bandwidth usage and growth projections
- Ensure gateway capacity for at least 150% peak concurrent connections
- Monitor and log failed connection attempts for security analysis
- Plan for geographic redundancy with multiple tunnel endpoints
- Implement traffic QoS policies to prioritize critical applications

## Conclusion

Proper VPN configuration is essential for secure enterprise network operations. Follow the procedures and standards outlined in this document to establish resilient, secure VPN infrastructure. Regularly review configurations against current security standards and organizational requirements to maintain protection against evolving threats.