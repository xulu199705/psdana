package csvio

import (
	"encoding/json"
	"fmt"
	"math"
	"strings"
	"testing"
)

func TestCSVSupportedFormats(t *testing.T) {
	tests := []struct {
		text     string
		config   CSVConfig
		expected []complex128
		kind     string
	}{
		{"0.25\n-0.5\n", DefaultConfig(), []complex128{0.25, -0.5}, "real"},
		{"sample\n0.25\n-0.5\n", DefaultConfig(), []complex128{0.25, -0.5}, "real"},
		{"\ufeffQ,I\n0.5,0.25\n", DefaultConfig(), []complex128{0.25 + 0.5i}, "complex"},
		{"q;i\n0.5;0.25\n", DefaultConfig(), []complex128{0.25 + 0.5i}, "complex"},
		{"i\tq\n0.25\t0.5\n", DefaultConfig(), []complex128{0.25 + 0.5i}, "complex"},
	}
	for _, format := range []string{"q15", "hex_q15"} {
		c := DefaultConfig()
		c.SampleFormat = format
		text := "i,q\n32767,-32768\n0,-1\n"
		if format == "hex_q15" {
			text = "q,i\n8000,7FFF\n0xFFFF,0000\n"
		}
		tests = append(tests, struct {
			text     string
			config   CSVConfig
			expected []complex128
			kind     string
		}{text, c, []complex128{32767.0/32768 - 1i, -1i / 32768}, "complex"})
	}
	c := DefaultConfig()
	c.InputType = "iq"
	tests = append(tests, struct {
		text     string
		config   CSVConfig
		expected []complex128
		kind     string
	}{"0.25,0.5\n", c, []complex128{0.25 + 0.5i}, "complex"})
	c = DefaultConfig()
	c.IColumn = &Column{Name: "real"}
	c.QColumn = &Column{Index: 2, ByIndex: true}
	tests = append(tests, struct {
		text     string
		config   CSVConfig
		expected []complex128
		kind     string
	}{"time,real,imag\n0,0.25,0.5\n", c, []complex128{0.25 + 0.5i}, "complex"})
	for j, test := range tests {
		t.Run(fmt.Sprint(j), func(t *testing.T) {
			d, err := Read(strings.NewReader(test.text), test.config)
			if err != nil {
				t.Fatal(err)
			}
			if d.InputType != test.kind || d.SampleCount() != len(test.expected) {
				t.Fatal("wrong representation/count")
			}
			for j, v := range test.expected {
				actual := complex(0, 0)
				if d.InputType == "complex" {
					actual = d.Complex[j]
				} else {
					actual = complex(d.Real[j], 0)
				}
				if actual != v {
					t.Fatalf("sample %d actual=%v expected=%v", j, actual, v)
				}
			}
		})
	}
}

func TestCSVInvalidInput(t *testing.T) {
	for j, text := range []string{"", "sample\n", "a,a\n1,2\n", "i,q\n1,2,3\n", "i,q\n1,\n", "nan\n1\n", "inf\n1\n", "sample\nNaN\n", "sample\nInf\n", "i,1\n1,2\n", "0.25,0.5\n", "time,real,imag\n0,1,2\n"} {
		t.Run(fmt.Sprint(j), func(t *testing.T) {
			if _, err := Read(strings.NewReader(text), DefaultConfig()); err == nil {
				t.Fatalf("accepted invalid CSV %q", text)
			}
		})
	}
	for _, format := range []string{"q15", "hex_q15"} {
		bad := []string{"32768", "-32769", "1.5"}
		if format == "hex_q15" {
			bad = []string{"10000", "-1", "GGGG"}
		}
		for _, s := range bad {
			c := DefaultConfig()
			c.SampleFormat = format
			if _, err := Read(strings.NewReader("sample\n"+s+"\n"), c); err == nil {
				t.Fatalf("accepted %s %s", format, s)
			}
		}
	}
	changes := []func(*CSVConfig){func(c *CSVConfig) { c.SampleFormat = "bad" }, func(c *CSVConfig) { c.Header = "bad" }, func(c *CSVConfig) { c.InputType = "bad" }, func(c *CSVConfig) { s := "::"; c.Delimiter = &s }, func(c *CSVConfig) { c.IColumn = &Column{Name: "i"} }, func(c *CSVConfig) { c.RealColumn = &Column{Index: 5, ByIndex: true} }, func(c *CSVConfig) {
		c.IColumn = &Column{Index: 0, ByIndex: true}
		c.QColumn = &Column{Index: 0, ByIndex: true}
	}, func(c *CSVConfig) {
		c.InputType = "real"
		c.IColumn = &Column{Name: "i"}
		c.QColumn = &Column{Name: "q"}
	}}
	for j, change := range changes {
		t.Run(fmt.Sprintf("config/%d", j), func(t *testing.T) {
			c := DefaultConfig()
			change(&c)
			if _, err := Read(strings.NewReader("i,q\n1,2\n"), c); err == nil {
				t.Fatal("invalid config accepted")
			}
		})
	}
	if _, err := ReadCSV("definitely_missing_file.csv", DefaultConfig()); err == nil {
		t.Fatal("missing file became zero input")
	}
}

func TestColumnJSONPreservesTypes(t *testing.T) {
	for _, raw := range []string{`"i"`, `0`, `-1`} {
		var c Column
		if err := json.Unmarshal([]byte(raw), &c); err != nil {
			t.Fatal(err)
		}
	}
	for _, raw := range []string{`1.0`, `true`, `null`} {
		var c Column
		if err := json.Unmarshal([]byte(raw), &c); err == nil {
			t.Fatal("invalid column accepted", raw)
		}
	}
	c := DefaultConfig()
	c.SampleFormat = "hex_q15"
	c.Header = "yes"
	c.IColumn = &Column{Name: "A"}
	c.QColumn = &Column{Name: "B"}
	d, err := Read(strings.NewReader("A,B\n7fff,8000\n"), c)
	if err != nil || math.Abs(real(d.Complex[0])-32767.0/32768) > 0 {
		t.Fatal("explicit hex-looking header failed", err)
	}
}
