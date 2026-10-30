package host

import (
	"testing"
	"time"
)

func TestCPUCountersExcludeGuestAndTreatIOWaitAsIdle(t *testing.T) {
	counters, err := parseCPU("cpu 100 0 100 800 50 10 20 20 1000 1000\ncpu0 1 2 3 4")
	if err != nil || counters.total != 1100 || counters.idle != 850 {
		t.Fatalf("unexpected counters: %+v %v", counters, err)
	}
	var sampler cpuSampler
	sampler.update(counters, time.Now())
	if sampler.percent != nil {
		t.Fatal("warmup must remain unknown")
	}
	sampler.update(cpuCounters{total: 1200, idle: 900}, time.Now())
	if sampler.percent == nil || *sampler.percent != 50 {
		t.Fatalf("expected 50 percent, got %v", sampler.percent)
	}
	sampler.update(cpuCounters{total: 1300, idle: 1000}, time.Now())
	if sampler.percent == nil || *sampler.percent != 0 {
		t.Fatal("real zero utilization must be preserved")
	}
	sampler.update(cpuCounters{total: 10, idle: 5}, time.Now())
	if sampler.percent != nil {
		t.Fatal("counter reset must discard sample")
	}
}
func TestInvalidCPUCounters(t *testing.T) {
	for _, text := range []string{"", "cpu0 1 2 3 4", "cpu 1 2", "cpu x 2 3 4"} {
		if _, err := parseCPU(text); err == nil {
			t.Fatalf("accepted invalid sample %q", text)
		}
	}
}
