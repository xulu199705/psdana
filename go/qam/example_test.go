package qam_test

import (
	"fmt"
	"github.com/xulu199705/psdana/go/qam"
	"math/cmplx"
)

func ExampleGenerateConstellation() {
	d, err := qam.GenerateConstellation(64)
	if err != nil {
		fmt.Println(err)
		return
	}
	_, indices, err := qam.SliceQAM(d, 64)
	if err != nil {
		fmt.Println(err)
		return
	}
	fmt.Println(len(d), indices[0], indices[63])
	// Output: 64 0 63
}

func ExampleGenerateRRCTaps() {
	h, err := qam.GenerateRRCTaps(.25, 10, 8)
	if err != nil {
		fmt.Println(err)
		return
	}
	energy := 0.0
	for _, v := range h {
		energy += v * v
	}
	fmt.Printf("%d %.3f %d\n", len(h), energy, (len(h)-1)/2)
	// Output: 81 1.000 40
}

func ExampleComputeQAMMetrics() {
	d, err := qam.GenerateConstellation(64)
	if err != nil {
		fmt.Println(err)
		return
	}
	y := make([]complex128, len(d))
	for k, v := range d {
		y[k] = v * (1.03 + .04i)
	}
	m, err := qam.ComputeQAMMetrics(y, d)
	if err != nil {
		fmt.Println(err)
		return
	}
	fmt.Printf("EVM %.3f%% radial %.3f%% tangential %.3f%%\n", m.EVMPctRMS, m.AmplitudeErrorPctRMS, m.PhaseErrorPctRMS)
	// Output: EVM 5.000% radial 3.000% tangential 4.000%
}

func ExampleScalarQAMFit() {
	d, err := qam.GenerateConstellation(64)
	if err != nil {
		fmt.Println(err)
		return
	}
	z := make([]complex128, len(d))
	for k, v := range d {
		z[k] = cmplx.Rect(.7, .3)*v + complex(.02, -.015)
	}
	cfg := qam.DefaultScalarConfig()
	cfg.DCMode = qam.DecisionDirectedJoint
	r, err := qam.ScalarQAMFit(z, cfg)
	if err != nil {
		fmt.Println(err)
		return
	}
	fmt.Printf("Joint EVM %.3f%%, converged %t\n", r.EVMPct, r.JointConverged)
	// Output: Joint EVM 0.000%, converged true
}
