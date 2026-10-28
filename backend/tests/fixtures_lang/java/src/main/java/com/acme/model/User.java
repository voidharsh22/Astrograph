package com.acme.model;

public class User extends Base implements Svc {
    private final String name;

    public User(String name) {
        this.name = name;
    }

    public String greet(String who) {
        touch();
        return "hi " + who;
    }

    public String greet(String who, int times) {
        return greet(who);
    }

    @Override
    public void run() {
    }

    public static class Builder {
        public User build() {
            return new User("built");
        }
    }

    public enum Level { LOW, HIGH }

    public record Point(int x, int y) {
    }
}
