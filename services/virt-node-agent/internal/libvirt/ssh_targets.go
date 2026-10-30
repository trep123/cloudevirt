package libvirt

import (
	"context"
	"net"
	"os"
	"strconv"
	"strings"
	"time"
)

// DomainSSHTargets excludes guest-agent/ARP claims: only MAC-bound DHCP leases qualify.
func (c *Client) DomainSSHTargets(ctx context.Context, name string) ([]string, error) {
	state, err := c.DomainState(ctx, name)
	if err != nil {
		return nil, err
	}
	result := []string{}
	if state != StateRunning {
		return result, nil
	}
	interfaces, err := c.DomainInterfaces(ctx, name)
	if err != nil {
		return nil, err
	}
	macs := map[string]bool{}
	for _, iface := range interfaces {
		macs[strings.ToLower(iface.MAC)] = true
	}
	seen := map[string]bool{}
	appendAddress := func(mac, address string) {
		ip := net.ParseIP(address)
		if macs[strings.ToLower(mac)] && safeSSHAddress(ip) && !seen[ip.String()] {
			seen[ip.String()] = true
			result = append(result, ip.String())
		}
	}
	output, err := c.run(ctx, "domifaddr", name, "--source", "lease")
	if err == nil {
		for _, item := range parseDomainAddresses(output) {
			appendAddress(item.MAC, item.Address)
		}
	}
	if c.LeaseFile != "" {
		data, err := os.ReadFile(c.LeaseFile)
		if err == nil {
			for _, line := range strings.Split(string(data), "\n") {
				fields := strings.Fields(line)
				if len(fields) < 3 {
					continue
				}
				expiry, err := strconv.ParseInt(fields[0], 10, 64)
				if err != nil || (expiry != 0 && expiry <= time.Now().Unix()) {
					continue
				}
				appendAddress(fields[1], fields[2])
			}
		}
	}
	return result, nil
}
func safeSSHAddress(ip net.IP) bool {
	if ip == nil || !ip.IsGlobalUnicast() || ip.IsLoopback() || ip.IsLinkLocalUnicast() {
		return false
	}
	addresses, err := net.InterfaceAddrs()
	if err != nil {
		return false
	}
	for _, address := range addresses {
		host, _, err := net.ParseCIDR(address.String())
		if err == nil && ip.Equal(host) {
			return false
		}
	}
	return true
}
