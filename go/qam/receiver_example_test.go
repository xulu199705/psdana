package qam_test

import (
	"fmt"
	"github.com/xulu199705/psdana/go/csvio"
	"github.com/xulu199705/psdana/go/qam"
)

func ExampleAnalyzeQAM() {
	csvConfig := csvio.DefaultConfig()
	csvConfig.SampleFormat = "q15"
	data, err := csvio.ReadCSV("../../data/generated/qam/Q13_32768_q15.csv", csvConfig)
	if err != nil {
		panic(err)
	}
	config := qam.DefaultQAMConfig()
	config.DCMode = qam.DecisionDirectedJoint
	result, err := qam.AnalyzeQAM(data.Complex, config)
	if err != nil {
		panic(err)
	}
	fmt.Println(result.QAMOrder, result.RecoveredSymbolCount, result.Diagnostics["status"])
	// Output: 64 4074 candidate
}
