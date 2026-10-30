package host

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

type cpuCounters struct{ total, idle uint64 }

func parseCPU(text string) (cpuCounters, error) {
	for _, line := range strings.Split(text, "\n") {
		fields := strings.Fields(line)
		if len(fields) == 0 || fields[0] != "cpu" {
			continue
		}
		if len(fields) < 5 {
			return cpuCounters{}, fmt.Errorf("incomplete cpu counters")
		}
		var result cpuCounters
		// guest/guest_nice are already included in user/nice; never count them twice.
		for i := 1; i < len(fields) && i <= 8; i++ {
			value, err := strconv.ParseUint(fields[i], 10, 64)
			if err != nil {
				return cpuCounters{}, err
			}
			result.total += value
			if i == 4 || i == 5 {
				result.idle += value
			}
		}
		return result, nil
	}
	return cpuCounters{}, fmt.Errorf("aggregate cpu counters missing")
}

type cpuSampler struct {
	sync.RWMutex
	previous  *cpuCounters
	percent   *float64
	sampledAt time.Time
}

func (s *cpuSampler) update(current cpuCounters, at time.Time) {
	s.Lock()
	defer s.Unlock()
	s.percent = nil
	if s.previous != nil && current.total > s.previous.total && current.idle >= s.previous.idle {
		total, idle := current.total-s.previous.total, current.idle-s.previous.idle
		if idle <= total {
			value := float64(total-idle) * 100 / float64(total)
			s.percent = &value
			s.sampledAt = at
		}
	}
	s.previous = &current
}
func (s *cpuSampler) read() {
	data, err := os.ReadFile("/proc/stat")
	if err == nil {
		var counters cpuCounters
		counters, err = parseCPU(string(data))
		if err == nil {
			s.update(counters, time.Now().UTC())
			return
		}
	}
	s.Lock()
	s.previous = nil
	s.percent = nil
	s.Unlock()
}

var cpuOnce sync.Once
var sampler cpuSampler

// CPUUsage never sleeps in an API request. A single process-wide sampler reads once/sec.
// Warmup and failed/stale samples remain null, not a fabricated zero.
func CPUUsage() (*float64, *time.Time) {
	cpuOnce.Do(func() {
		sampler.read()
		go func() {
			ticker := time.NewTicker(time.Second)
			defer ticker.Stop()
			for range ticker.C {
				sampler.read()
			}
		}()
	})
	sampler.RLock()
	defer sampler.RUnlock()
	if sampler.percent == nil || time.Since(sampler.sampledAt) > 5*time.Second {
		return nil, nil
	}
	percent, sampledAt := *sampler.percent, sampler.sampledAt
	return &percent, &sampledAt
}
