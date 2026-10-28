package com.acme.app;

import static com.acme.util.Strings.shout;

import com.acme.model.*;
import com.acme.model.User;
import org.external.Lib;

public class Main {
    private final User user = new User("field");

    public void main(String[] args) {
        User u = new User("x");
        u.greet("a");
        u.greet("a", 2);
        u.id();
        u.run();
        shout("x");
        helper();
        new User.Builder().build();
        Lib.go();
        Unknown.call();
        user.greet("f");
    }

    private void helper() {
    }
}
