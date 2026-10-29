package storage

import (
	"fmt"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"net"
)

type GuestNetwork struct {
	MAC          string   `json:"mac"`
	Name         string   `json:"name"`
	DHCP4        bool     `json:"dhcp4"`
	Address      string   `json:"address"`
	Gateway      string   `json:"gateway"`
	DNS          []string `json:"dns"`
	DefaultRoute bool     `json:"default_route"`
}

func GuestNetworkConfig(networks []GuestNetwork) (map[string]any, error) {
	if len(networks) > 8 {
		return nil, apierr.New(apierr.CodeInvalidArgument, "网卡数量超限", nil)
	}
	ethernets := map[string]any{}
	seen := map[string]bool{}
	defaults := 0
	for index, nic := range networks {
		mac, err := net.ParseMAC(nic.MAC)
		if err != nil || len(mac) != 6 || mac[0]&1 != 0 || seen[mac.String()] || nic.Name != fmt.Sprintf("cvnet%d", index) {
			return nil, apierr.New(apierr.CodeInvalidArgument, "初始化网卡标识无效", err)
		}
		seen[mac.String()] = true
		if nic.DefaultRoute {
			defaults++
		}
		config := map[string]any{"match": map[string]string{"macaddress": mac.String()}, "set-name": nic.Name, "dhcp4": nic.DHCP4}
		if nic.DHCP4 {
			config["dhcp4-overrides"] = map[string]any{"use-routes": nic.DefaultRoute, "route-metric": 100 + index*100}
		} else {
			ip, subnet, err := net.ParseCIDR(nic.Address)
			gateway := net.ParseIP(nic.Gateway)
			if err != nil || ip.To4() == nil || gateway == nil || gateway.To4() == nil || !subnet.Contains(gateway) || ip.Equal(gateway) {
				return nil, apierr.New(apierr.CodeInvalidArgument, "静态网络地址或网关无效", err)
			}
			config["addresses"] = []string{nic.Address}
			if nic.DefaultRoute {
				config["routes"] = []map[string]any{{"to": "default", "via": nic.Gateway, "metric": 100 + index*100}}
			}
			if len(nic.DNS) > 4 {
				return nil, apierr.New(apierr.CodeInvalidArgument, "DNS 数量超限", nil)
			}
			for _, dns := range nic.DNS {
				if net.ParseIP(dns) == nil {
					return nil, apierr.New(apierr.CodeInvalidArgument, "DNS 地址无效", nil)
				}
			}
			if len(nic.DNS) > 0 {
				config["nameservers"] = map[string]any{"addresses": nic.DNS}
			}
		}
		ethernets[nic.Name] = config
	}
	if defaults > 1 {
		return nil, apierr.New(apierr.CodeInvalidArgument, "默认路由重复", nil)
	}
	return map[string]any{"version": 2, "ethernets": ethernets}, nil
}
