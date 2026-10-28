pub mod role;

pub use role::Role;

pub trait Greeter {
    fn greet(&self);
}

pub struct User {
    pub name: String,
}

impl User {
    pub fn new(name: &str) -> Self {
        User { name: name.to_string() }
    }
}

impl Greeter for User {
    fn greet(&self) {}
}
