// Command webdemo serves the embedded V2.2.0 UI and the existing Go analyzers.
package main

import (
	"embed"
	"io/fs"
	"log"
	"net/http"
	"time"
)

//go:embed static
var assets embed.FS

func main() {
	server := &http.Server{Addr: "127.0.0.1:8080", Handler: newHandler(maxRequestBytes),
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 60 * time.Second, IdleTimeout: 60 * time.Second}
	log.Print("PSDANA V2.2.0: http://127.0.0.1:8080")
	log.Fatal(server.ListenAndServe())
}

func newHandler(limit int64) http.Handler {
	static, err := fs.Sub(assets, "static")
	if err != nil {
		panic(err)
	}
	mux := http.NewServeMux()
	mux.Handle("GET /", http.FileServer(http.FS(static)))
	mux.HandleFunc("GET /api/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "version": "2.2.0"})
	})
	a := &analyzer{limit: limit, slots: make(chan struct{}, 1)}
	mux.HandleFunc("POST /api/analyze", a.analyze)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'")
		mux.ServeHTTP(w, r)
	})
}
