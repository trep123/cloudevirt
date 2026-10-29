package storage

import "testing"

func TestGuestNetworkMatchesMACAndSuppressesExtraDefaultRoutes(t *testing.T) {
	networks := []GuestNetwork{{MAC: "02:00:00:00:00:01", Name: "cvnet0", Address: "10.22.0.10/24", Gateway: "10.22.0.1", DNS: []string{"10.22.0.1"}, DefaultRoute: true}, {MAC: "02:00:00:00:00:02", Name: "cvnet1", DHCP4: true}}
	config, err := GuestNetworkConfig(networks)
	if err != nil {
		t.Fatal(err)
	}
	nics := config["ethernets"].(map[string]any)
	primary := nics["cvnet0"].(map[string]any)
	secondary := nics["cvnet1"].(map[string]any)
	if primary["match"].(map[string]string)["macaddress"] != networks[0].MAC || len(primary["routes"].([]map[string]any)) != 1 || secondary["dhcp4-overrides"].(map[string]any)["use-routes"] != false {
		t.Fatal("wrong route or MAC binding")
	}
	networks[1].DefaultRoute = true
	if _, err := GuestNetworkConfig(networks); err == nil {
		t.Fatal("accepted multiple default routes")
	}
	networks[1].DefaultRoute = false
	networks[1].MAC = networks[0].MAC
	if _, err := GuestNetworkConfig(networks); err == nil {
		t.Fatal("accepted duplicate MAC")
	}
	networks = networks[:1]
	networks[0].Gateway = "192.168.4.1"
	if _, err := GuestNetworkConfig(networks); err == nil {
		t.Fatal("accepted gateway outside subnet")
	}
}
