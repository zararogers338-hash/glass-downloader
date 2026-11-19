#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use tauri::{WebviewUrl, WebviewWindowBuilder};

fn main() {
    let Ok(raw) = std::env::var("GLASS_START_URL") else {
        eprintln!("Run start.cmd or python launch.py to start the local service.");
        return;
    };
    let Ok(url) = raw.parse::<tauri::Url>() else { return };
    if url.scheme() != "http" || url.host_str() != Some("127.0.0.1") { return; }
    let origin = url.origin();
    tauri::Builder::default().setup(move |app| {
        WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
            .title("泊岸 · 下载工作台").inner_size(1420., 890.).min_inner_size(840., 580.)
            .on_navigation(move |dest| dest.origin() == origin)
            .build()?;
        Ok(())
    }).run(tauri::generate_context!()).expect("Desktop window failed");
}
