const User = require('../models/User.model');
const jwt = require('jsonwebtoken');

// Helper function to generate JWT
const generateToken = (userId) => {
    return jwt.sign({ id: userId }, process.env.JWT_SECRET, { expiresIn: '7d' });
};

exports.register = async (req, res) => {
    try {
        const { email, password } = req.body;

        if (!email?.trim() || !password?.trim()) {
            return res.status(400).json({ error: { code: 400, message: 'Email and password are required' } });
        }

        if ([email, password].some((field) => field?.trim() === "" || field === undefined)) {
            return res.status(400).json({ error: { code: 400, message: 'All fields are required and cannot be empty' } });
        }

        const emailNorm = email.toLowerCase().trim();
        const existedUser = await User.findOne({ email: emailNorm });
        if (existedUser) {
            return res.status(409).json({ error: { code: 409, message: 'User with this email already exists' } });
        }

        const user = await User.create({ 
            email: emailNorm, 
            password 
        });

        const createdUser = await User.findById(user._id).select("-password");

        if (!createdUser) {
            return res.status(500).json({ error: { code: 500, message: 'Something went wrong while registering the user' } });
        }

        return res.status(201).json({
            message: "User Registered Successfully"
        });

    } catch (error) {
        console.error("Registration Error:", error);
        res.status(500).json({ error: { code: 500, message: 'Server error during registration' } });
    }
};

exports.login = async (req, res) => {
    try {
        const { email, password } = req.body;
    
        if (!email?.trim() || !password?.trim()) {
            return res.status(400).json({ error: { code: 400, message: 'Email and password are required' } });
        }

        const emailNorm = email.toLowerCase().trim();
        // Lookup with the same normalization register applies, else a case
        // difference would silently 401.
        const user = await User.findOne({ email: emailNorm });

        if (!user || !(await user.comparePassword(password))) {
            return res.status(401).json({ error: { code: 401, message: 'Invalid email or password' } });
        }

        const token = generateToken(user._id);

        // secure cookies are HTTPS-only; a hardcoded true would drop the cookie
        // over local dev HTTP and lock the user out.
        const isProduction = process.env.NODE_ENV === 'production';
        res.cookie('token', token, {
            httpOnly: true,
            secure: isProduction,
            sameSite: isProduction ? 'strict' : 'lax',
            maxAge: 7 * 24 * 60 * 60 * 1000
        });

        res.status(200).json({
            message: "Login successful",
            user: { id: user._id, email: user.email }
        });
    } catch (error) {
        res.status(500).json({ error: { code: 500, message: 'Server error during login' } });
    }
};

exports.logout = async (req, res) => {
    try {
        res.clearCookie('token');
        return res.status(200).json({ message: "Successfully logged out." });
    } catch (error) {
        res.status(500).json({ error: { code: 500, message: 'Server error during logout' } });
    }
};