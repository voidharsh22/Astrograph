use std::collections::HashMap;

mod models;
mod util;

use models::{Role as R, User};
use util::helper;

fn main() {
    let u = User::new("x");
    u.greet();
    helper();
    crate::util::other();
    println!("hello");
    missing::call();
}
