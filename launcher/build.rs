fn main() {
    println!("cargo:rerun-if-changed=assets/rabbit-logo.ico");

    #[cfg(windows)]
    {
        let mut resource = winresource::WindowsResource::new();
        resource.set_icon("assets/rabbit-logo.ico");
        resource.set("FileDescription", "iLab CONJURE");
        resource.set("ProductName", "iLab CONJURE");
        resource.set("CompanyName", "iLab");
        resource.set("OriginalFilename", "iLab GPT CONJURE.exe");
        resource
            .compile()
            .expect("failed to embed Windows launcher resources");
    }
}
